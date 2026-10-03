"""
All routes for the Flask application.
This file contains every route in one place for simplicity.
"""

import os
import re
import sqlite3

from flask import render_template, request, redirect, url_for, flash, jsonify, session
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from run import app
from models.user import create_user, get_user, update_last_login, update_avatar
from utils import login_required, no_cache
from vaccination_functions import get_vaccination_by_date, create_vac_by_map_fig, create_vac_by_state_fig, update_graph_layout, get_vaccination_by_state_time
from disease_functions import display_disease_cases_over_time, display_cumulative_disease_cases_graph, get_disease_cases_over_time, get_cumulative_disease_cases
import plotly.express as px
from cache import cache_ready
from ai_client import client, create_prompt, convert_df
import json
import pandas as pd
import requests
from dataset_workspace import workspace_context, upload_dataset, retry_analysis
from saved_charts import favorites_context, update_favorite
from auth_limits import init_auth_limits, limiter
from form_security import init_form_security
from public_chart_data import PAGE_DETAILS, get_chart_payload

init_auth_limits(app)
init_form_security(app)

AVATAR_OPTIONS = {
    "blue": {"emoji": "🧭", "label": "Blue compass"},
    "green": {"emoji": "🌿", "label": "Green leaf"},
    "purple": {"emoji": "🔬", "label": "Purple microscope"},
    "orange": {"emoji": "📊", "label": "Orange chart"},
    "red": {"emoji": "🩺", "label": "Red stethoscope"},
}


@app.context_processor
def inject_user_navigation():
    """Make the signed-in user's profile available in the shared header."""
    user = None
    if session.get("user_id"):
        user = get_user(user_id=session["user_id"])
    return {"current_user": user, "avatar_options": AVATAR_OPTIONS}

# ========== MAIN PAGES ==========

@app.context_processor
def inject_saved_charts():
    if request.endpoint in ('dashboard', 'vaccination_page', 'disease_page', 'nutrition_page'):
        try:
            return favorites_context()
        except (sqlite3.Error, OSError):
            if request.endpoint not in ('vaccination_page', 'disease_page'):
                raise
            app.logger.exception("Saved chart storage unavailable on public data page")
            return {'saved_charts': [], 'saved_chart_ids': [], 'favorites_unavailable': True}
    return {}


@app.route('/charts/<chart_id>/favorite', methods=['POST'])
@login_required
@no_cache
def chart_favorite(chart_id):
    return update_favorite(chart_id)

@app.route('/')
def home():
    """Home page"""
    return render_template('landing.html')


@app.route('/about')
def about():
    """About page"""
    return render_template('about.html')


@app.route('/dashboard')
@login_required
@no_cache
def dashboard():
    """Private landing page for signed-in users."""
    user = get_user(user_id=session['user_id'])
    if user is None:
        session.clear()
        flash("Your session is no longer valid. Please sign in again.", "warning")
        return redirect(url_for('signin'))

    return render_template('dashboard.html', user=user, **workspace_context(session['user_id']))


@app.route('/dashboard/upload', methods=['POST'])
@login_required
@no_cache
def dashboard_upload():
    return upload_dataset()


@app.route('/dashboard/datasets/<int:dataset_id>/analyze', methods=['POST'])
@login_required
@no_cache
def dashboard_analyze(dataset_id):
    return retry_analysis(dataset_id)




@app.route('/signin', methods=['GET', 'POST'])
@limiter.limit('5 per minute; 30 per hour', methods=['POST'])
def signin():
    """Sign users in with either their username or email address."""
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        if len(identifier) > 254 or len(password) > 256:
            flash("Username, email, or password is incorrect.", "danger")
            return redirect(url_for('signin'))

        if not identifier or not password:
            flash("Username or email and password are required!", "danger")
            return redirect(url_for('signin'))

        user = get_user(username=identifier) or get_user(email=identifier)
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session.permanent = "remember" in request.form
            update_last_login(str(datetime.now()), user['user_id'])
            session['user_id'] = user['user_id']
            flash("Successfully signed in!", "success")
            return redirect(url_for('dashboard'))

        flash("Username, email, or password is incorrect.", "danger")
        return redirect(url_for('signin'))

    return render_template('signin.html')

# ========== AUTHENTICATION ==========

@app.route('/login')
def legacy_login():
    """Send old login links to the canonical sign-in page."""
    return redirect(url_for('signin'))


@app.route("/signup", methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def signup():
    """Signup Page"""
    if request.method == "POST":
        if request.form.get("educational_acknowledgment") != "accepted":
            flash("Please acknowledge the educational project disclaimer to create an account.", "danger")
            return redirect(url_for('signup'))

        error = False
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        email = request.form.get("email", "").strip()
        if not email:
            email = None

        if not 3 <= len(username) <= 40 or any(ord(c) < 32 or ord(c) == 127 for c in username):
            flash("Choose a username between 3 and 40 characters without control characters.", "danger")
            error = True
        if not 7 <= len(password) <= 256:
            flash("Choose a password between 7 and 256 characters.", "danger")
            error = True
        if email and (len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
            flash("Enter a valid email address or leave it blank.", "danger")
            error = True
        if error:
            return redirect(url_for('signup'))
            
        if get_user(username=username) is not None:
            flash("Username is already taken!", "danger")
            error = True
        
        if email and get_user(email=email) is not None:
            flash("Email is already registered!", "danger")
            error = True

        if error:
            return redirect(url_for('signup'))
        
        hashed_password = generate_password_hash(password)
        cur_time = str(datetime.now())

        create_user_result = create_user(username=username, pasword_hash=hashed_password, created_at=cur_time, email=email)

        if create_user_result:
            flash("We could not create that account. Please try a different username or email.", "danger")
            return redirect(url_for('signup'))
        
        flash("Account created!", "success")
        return redirect(url_for('signin'))
    
    else:
        return render_template("signup.html")


@app.route('/logout', methods=['GET', 'POST'])
@no_cache
def logout():
    if request.method == 'GET':
        return render_template('logout.html')
    session.clear()
    return redirect(url_for('signin'))


@app.route('/profile/avatar', methods=['POST'])
@login_required
@no_cache
def select_avatar():
    avatar = request.form.get("avatar", "")
    if avatar not in AVATAR_OPTIONS:
        flash("Please choose a valid profile avatar.", "danger")
    elif not update_avatar(avatar, session["user_id"]):
        flash("We could not update your profile avatar.", "danger")

    next_page = request.form.get("next", "")
    allowed_pages = {url_for(endpoint) for endpoint in ('home', 'about', 'dashboard', 'nutrition_page', 'disease_page', 'vaccination_page')}
    if next_page not in allowed_pages:
        next_page = url_for("dashboard")
    return redirect(next_page)




# ========== API ENDPOINTS ==========

@app.route('/healthz', methods=['GET'])
def healthz():
    """Public liveness check; does not require a session or database query."""
    return "OK", 200

@app.route('/api/health')
def health_check():
    """Check if app is running"""
    return jsonify({'status': 'ok', 'message': 'App is running!'})


def get_nutrition_data():
    """Fetch live nutrition data from USDA when configured, otherwise use Open Food Facts."""
    usda_key = (os.getenv("USDA_API_KEY") or "").strip()
    query_terms = ["milk", "eggs", "rice", "spinach", "sweet potato"]

    try:
        if usda_key:
            query = " ".join(query_terms)
            response = requests.get(
                "https://api.nal.usda.gov/fdc/v1/foods/search",
                params={
                    "api_key": usda_key,
                    "query": query,
                    "pageSize": 25,
                    "sortBy": "publishedDate",
                    "sortOrder": "desc",
                },
                headers={"accept": "application/json"},
                timeout=20,
            )
            response.raise_for_status()
            foods = response.json().get("foods", [])
            rows = []
            for food in foods[:10]:
                food_nutrients = {
                    n.get("nutrientName"): n.get("value", 0)
                    for n in food.get("foodNutrients", [])
                    if n.get("nutrientName")
                }
                rows.append({
                    "date": (food.get("publishedDate") or datetime.utcnow().strftime("%Y-%m-%d")),
                    "product_name": food.get("description", "Unknown product"),
                    "energy_kcal": food_nutrients.get("Energy", 0),
                    "protein_g": food_nutrients.get("Protein", 0),
                    "carbohydrates_g": food_nutrients.get("Carbohydrate, by difference", 0),
                    "fat_g": food_nutrients.get("Total lipid (fat)", 0),
                })
            if rows:
                return pd.DataFrame(rows)

        response = requests.get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={
                "search_terms": " ".join(query_terms),
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": 20,
            },
            timeout=20,
        )
        response.raise_for_status()

        products = response.json().get("products", [])
        rows = []
        for product in products[:10]:
            nutriments = product.get("nutriments", {})
            rows.append({
                "date": (product.get("last_modified_t") and datetime.fromtimestamp(product.get("last_modified_t", 0)).strftime("%Y-%m-%d")) or datetime.utcnow().strftime("%Y-%m-%d"),
                "product_name": product.get("product_name", "Unknown product"),
                "energy_kcal": nutriments.get("energy-kcal_100g", 0),
                "protein_g": nutriments.get("proteins_100g", 0),
                "carbohydrates_g": nutriments.get("carbohydrates_100g", 0),
                "fat_g": nutriments.get("fat_100g", 0),
            })
        if rows:
            return pd.DataFrame(rows)
    except Exception:
        pass

    return pd.DataFrame(
        {
            "date": pd.date_range("2023-01-01", periods=6, freq="MS"),
            "product_name": [
                "Milk",
                "Yogurt",
                "Eggs",
                "Rice",
                "Sweet potato",
                "Spinach",
            ],
            "energy_kcal": [60, 100, 155, 130, 90, 25],
            "protein_g": [3.4, 8.5, 13, 2.7, 2.1, 2.9],
            "carbohydrates_g": [4.8, 4.5, 1.1, 28, 20, 3.6],
            "fat_g": [3.2, 4.2, 11, 0.3, 0.1, 0.4],
        }
    )


@app.route("/nutrition", methods=['GET', 'POST'])
@login_required
@no_cache
def nutrition_page():
    nutrition_df = get_nutrition_data()
    nutrition_df = nutrition_df.copy()
    nutrition_df["date"] = pd.to_datetime(nutrition_df["date"])
    for column in ["energy_kcal", "protein_g", "carbohydrates_g", "fat_g"]:
        nutrition_df[column] = pd.to_numeric(nutrition_df.get(column, 0), errors="coerce").fillna(0)

    nutrition_time_df = (
        nutrition_df.groupby("date", as_index=False)
        .agg(
            energy_kcal=("energy_kcal", "mean"),
            protein_g=("protein_g", "mean"),
            carbohydrates_g=("carbohydrates_g", "mean"),
            fat_g=("fat_g", "mean"),
        )
        .sort_values("date")
    )

    nutrition_over_time_fig = px.line(
        nutrition_time_df,
        x="date",
        y="energy_kcal",
        title="Energy Intake Over Time (USDA/Open Food Facts)",
        labels={"date": "Date", "energy_kcal": "Energy (kcal/100g)"},
        markers=True,
    )
    nutrition_over_time_fig.update_layout(height=500, autosize=True, margin={"l": 20, "r": 20, "t": 50, "b": 20})
    nutrition_over_time_graph = nutrition_over_time_fig.to_html(full_html=False, config={"responsive": True})

    state_codes = ["CA", "TX", "FL", "NY", "WA", "CO", "NH"]
    state_rows = nutrition_df.head(len(state_codes)).reset_index(drop=True)
    state_df = pd.DataFrame({
        "state": state_codes[: len(state_rows)],
        "product_name": state_rows["product_name"].fillna("Unknown product").tolist(),
        "energy_kcal": state_rows["energy_kcal"].tolist(),
        "protein_g": state_rows["protein_g"].tolist(),
        "carbohydrates_g": state_rows["carbohydrates_g"].tolist(),
        "fat_g": state_rows["fat_g"].tolist(),
    })
    state_df["summary"] = state_df["product_name"].astype(str) + " — " + state_df["state"].astype(str)

    nutrition_by_state_fig = px.bar(
        state_df,
        x="state",
        y="protein_g",
        color="energy_kcal",
        title="Protein Density by State Summary",
        labels={"state": "State", "protein_g": "Protein (g/100g)", "energy_kcal": "Energy (kcal/100g)"},
        hover_name="summary",
        color_continuous_scale="Viridis",
    )
    nutrition_by_state_fig.update_layout(height=500, autosize=True, margin={"l": 20, "r": 20, "t": 50, "b": 20})
    nutrition_by_state_graph = nutrition_by_state_fig.to_html(full_html=False, config={"responsive": True})

    nutrition_by_state_map_fig = px.choropleth(
        state_df,
        locations="state",
        locationmode="USA-states",
        color="energy_kcal",
        scope="usa",
        title="Energy Intake by State Summary",
        labels={"energy_kcal": "Energy (kcal/100g)"},
        hover_name="summary",
        color_continuous_scale="YlGnBu",
    )
    nutrition_by_state_map_fig.update_layout(height=500, autosize=True, margin={"l": 20, "r": 20, "t": 50, "b": 20})
    nutrition_by_state_map = nutrition_by_state_map_fig.to_html(full_html=False, config={"responsive": True})

    analyses = {}
    if request.method == "POST":
        graphs = {
            "nutrition_over_time": (
                nutrition_over_time_fig.layout.title.text,
                nutrition_time_df[["date", "energy_kcal"]],
                "nutrition_over_time_analysis",
            ),
            "nutrition_state_bar": (
                nutrition_by_state_fig.layout.title.text,
                state_df[["state", "product_name", "protein_g", "energy_kcal"]],
                "nutrition_state_bar_analysis",
            ),
            "nutrition_state_map": (
                nutrition_by_state_map_fig.layout.title.text,
                state_df[["state", "product_name", "energy_kcal"]],
                "nutrition_state_map_analysis",
            ),
        }
        graph = graphs.get(request.form.get("data"))
        if graph is None:
            flash("Choose a nutrition chart to analyze.", "warning")
        elif client is None:
            flash("AI analysis is currently unavailable. Please try again later.", "warning")
        else:
            title, chart_data, analysis_key = graph
            context = (
                "These are food product nutrient values per 100 g, not population intake "
                "or dietary deficiency measurements. Dates are product publication dates, "
                "not observations of changes in people's diets. State labels are assigned "
                "to product records for demonstration and do not indicate where the foods "
                "were consumed or measured. Do not infer state differences in health or "
                "geographic patterns. Explain these limitations when relevant."
            )
            try:
                prompt = create_prompt(title, convert_df(chart_data.copy()))
                completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": context},
                        {"role": "user", "content": prompt},
                    ],
                    model="openai/gpt-oss-20b",
                    max_completion_tokens=4096,
                )
                analysis = completion.choices[0].message.content
                if not analysis or not analysis.strip():
                    raise ValueError("Empty nutrition analysis")
                analyses[analysis_key] = analysis.strip()
            except Exception:
                app.logger.warning("Nutrition AI analysis failed", exc_info=True)
                flash("We could not analyze this chart. Please try again.", "danger")

    return render_template(
        "nutrition.html",
        nutrition_over_time_graph=nutrition_over_time_graph,
        nutrition_by_state_graph=nutrition_by_state_graph,
        nutrition_by_state_map=nutrition_by_state_map,
        **analyses,
    )


@app.route("/nutrition-status")
def nutrition_status():
    return {"ready": True}


@app.route("/vaccinations", methods=['GET', 'POST'])
@login_required
@no_cache
def vaccination_page():
    if request.method == "GET":
        return render_template("public_data.html", page="vaccinations", details=PAGE_DETAILS["vaccinations"])
    
    try:
        # vac over time
        vaccination_over_time = get_vaccination_by_date()
        over_time_graph_fig = px.line(
            vaccination_over_time,
            x="date",
            y="avg_vaccination_rate",
            title="COVID-19 Vaccination Rate Over Time",
            labels={
            "date": "Date",
            "avg_vaccination_rate": "Vaccination Rate (%)"
        }
        )
    
        update_graph_layout(over_time_graph_fig)

        over_time_graph = over_time_graph_fig.to_html(
            full_html=False,
            config={"responsive": True})
    
        # vac by state
    
        vac_by_state_time = get_vaccination_by_state_time()
    
        by_state_graph = create_vac_by_state_fig(vac_by_state_time)
        by_state_map = create_vac_by_map_fig(vac_by_state_time)
    
    
    except Exception:
        app.logger.exception("Vaccination charts unavailable during analysis")
        flash("Recent CDC data could not be loaded. Use the saved demo data below.", "warning")
        return render_template("public_data.html", page="vaccinations", details=PAGE_DETAILS["vaccinations"])

    analyses = {}
    if request.method == "POST":
        choices = {
            "over_time": ("COVID-19 Vaccination Rate Over Time", vaccination_over_time, "over_time_analysis"),
            "state_time_bar": ("COVID-19 Vaccination Rate by State", vac_by_state_time, "state_time_bar_analysis"),
            "state_time_map": ("COVID-19 Vaccination Coverage Map", vac_by_state_time, "state_time_map_analysis"),
        }
        graph = choices.get(request.form.get("data"))
        if graph is None:
            flash("Choose a vaccination chart to analyze.", "warning")
        else:
            title, frame, analysis_key = graph
            analysis = analyze_public_chart(title, frame)
            if analysis:
                analyses[analysis_key] = analysis
    return render_template("vaccinations.html", over_time_graph=over_time_graph,
                           by_state_graph=by_state_graph, by_state_map=by_state_map, **analyses)

@app.route("/vaccination-status")
def vaccination_status():
    return {
        "ready": cache_ready.is_set()
    }
    
@app.route("/diseases", methods=['GET', 'POST'])
@login_required
@no_cache
def disease_page():
    if request.method == "GET":
        return render_template("public_data.html", page="diseases", details=PAGE_DETAILS["diseases"])
    monthly_disease_df = cumulative_df = None
    latest_year = None
    over_time_graph = cumulative_cases_graph = None
    notices = {}
    try:
        monthly_disease_df = get_disease_cases_over_time()
        over_time_graph = display_disease_cases_over_time(monthly_disease_df)
    except Exception:
        app.logger.exception("Disease trend chart failed")
        monthly_disease_df = None
    try:
        cumulative_df, latest_year = get_cumulative_disease_cases()
        cumulative_cases_graph = display_cumulative_disease_cases_graph(cumulative_df, latest_year)
    except Exception:
        app.logger.exception("Cumulative disease chart failed")
        cumulative_df = None
    for name, frame in (("over_time", monthly_disease_df), ("cumulative", cumulative_df)):
        if frame is not None and frame.attrs.get("stale"):
            fetched = datetime.fromtimestamp(frame.attrs["fetched_at"], tz=timezone.utc)
            notices[name] = "CDC refresh is temporarily unavailable. Showing saved data fetched " + fetched.strftime("%Y-%m-%d %H:%M UTC") + "."
    analyses = {}
    if request.method == "POST":
        choices = {
            "over_time": ("Disease Cases Over Time", monthly_disease_df, "over_time_graph_analysis"),
            "cumulative_cases": (f"Cumulative Disease Cases in {latest_year}", cumulative_df, "cumulative_cases_graph_analysis"),
        }
        graph = choices.get(request.form.get("data"))
        if graph is None:
            flash("Choose a disease chart to analyze.", "warning")
        else:
            title, frame, analysis_key = graph
            if frame is None:
                flash("This chart's data is temporarily unavailable. Please try again shortly.", "warning")
                analysis = None
            else:
                analysis = analyze_public_chart(title, frame)
            if analysis:
                analyses[analysis_key] = analysis
    return render_template("diseases.html", over_time_graph=over_time_graph,
                           cumulative_cases_graph=cumulative_cases_graph, disease_notices=notices, **analyses)


@app.route('/api/public-charts/<page>')
@login_required
@no_cache
def public_charts(page):
    if page not in PAGE_DETAILS:
        return jsonify(error="Unknown data page"), 404
    try:
        return jsonify(get_chart_payload(page))
    except Exception:
        app.logger.exception("Recent chart data unavailable for %s", page)
        return jsonify(error="Recent CDC data is temporarily unavailable. Use the saved demo data."), 503


def analyze_public_chart(title, frame):
    """Analyze only server-selected chart data during a CSRF-protected POST."""
    if client is None:
        flash("AI analysis is currently unavailable. Please try again later.", "warning")
        return None
    try:
        completion = client.with_options(timeout=45, max_retries=0).chat.completions.create(
            messages=[{"role": "user", "content": create_prompt(title, convert_df(frame.copy()))}],
            model="openai/gpt-oss-20b", max_completion_tokens=4096,
        )
        content = completion.choices[0].message.content
        if not content or not content.strip():
            raise ValueError("Empty chart analysis")
        return content.strip()
    except Exception:
        app.logger.warning("Public chart analysis failed")
        flash("We could not analyze this chart. Please try again.", "danger")
        return None


@app.route("/ai-analysis")
@login_required
@no_cache
def ai_analysis():
    # Old bookmarks remain navigable, but GET never triggers a paid AI request.
    return redirect(url_for('dashboard'))


# ========== OTHER ROUTES ==========
@app.errorhandler(404)
def error_404(e):
    return render_template("404.html"), 404
