import os
from dotenv import load_dotenv
from groq import Groq
import json
import tiktoken
import pandas as pd


load_dotenv()


def get_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to your .env file or environment variables before using AI analysis."
        )
    return Groq(api_key=api_key)


client = None
try:
    client = get_client()
except RuntimeError:
    client = None


def create_prompt(graph_title, table_data):
    prompt = f"""
    You are an AI data analyst integrated into a public-health data dashboard. Analyze the currently displayed graph and provide a concise, insightful interpretation that helps the user understand what the data shows and how it relates to the real world.

    Graph Title:
    {graph_title}

    Graph Data:
    {table_data}

    Use the following structure:

    📈 Key Trends
    Identify the most important patterns, trends, or changes visible in the data. Use specific values, dates, and percentage changes when they meaningfully support your observations.

    ⚠️ Notable Changes
    Identify significant spikes, drops, outliers, unusual values, or other observations that stand out. Do not force an anomaly if the data does not contain one.

    🌎 Real-World Context
    Use relevant established real-world knowledge to help explain or contextualize the patterns you observed. Explain possible reasons for the trends when appropriate, but clearly distinguish established explanations from plausible possibilities. Do not claim that a factor caused a trend unless there is sufficient evidence to support causation.

    💡 Takeaway
    Give the user the most important overall insight from the graph in a concise, understandable way.

    Rules:

    Base observations about the graph strictly on the provided data.
    Do not invent, estimate, or extrapolate numerical values.
    Use the full time range when evaluating trends.
    Distinguish long-term trends from short-term fluctuations and seasonal patterns.
    Avoid repeating the same observation across multiple sections.
    Do not overstate conclusions or imply causation without sufficient evidence.
    Use relevant real-world knowledge for context, but clearly distinguish facts from possible explanations.
    If the data does not support a meaningful conclusion, say so rather than inventing one.
    Keep the response concise and easy to read.
    Do not include introductory, conversational, or meta-commentary. Begin immediately with "📈 Key Trends" and do not say things such as "Here is your analysis," "Sure, I can help," or similar phrases.
    Do not use Markdown syntax such as hashtags, asterisks, backticks, or Markdown bullet formatting. Use plain text only.
    - Format large numbers using commas as thousands separators (e.g., 23,560 and 1,400,000). Never use spaces as thousands separators.
    - Format decimal numbers using a period (e.g., 23.56).
    - Be concise and focus only on the most meaningful insights from the graph. The analysis should feel like a quick, useful explanation for someone viewing the dashboard, not a detailed report. 
        Generally aim for around 100–175 words, but use less when the graph is simple and somewhat more when the data contains genuinely important patterns that require explanation. 
        Never add filler, repeat observations, or include details that do not meaningfully help the user understand the graph.
    - Keep the response reasonably concise even when the dataset is large. 
        As a general guideline, do not exceed 300 words unless the graph contains unusually complex or important patterns that genuinely require additional explanation. 
        This is a flexible upper limit, not a target or required range. 
        Never increase the length of a response simply to approach the limit, and never add filler, repetition, or unnecessary explanation to use more of the available space.       
    """
    return prompt

def check_tokens(prompt):
    encoder = tiktoken.get_encoding("o200k_base")
    
    # Encode text to tokens
    token_list = encoder.encode(prompt)
    tokens = len(token_list)
    if tokens >= 2000:
        return True
    else:
        return False
    
        

def convert_df(df):
    date_cols = df.select_dtypes(include=["datetime"]).columns
    df[date_cols] = df[date_cols].astype(str)
    
    num_cols = df.select_dtypes(include=['int', 'int64', 'int32', 'float', 'float64', 'float32']).columns
    df[num_cols] = df[num_cols].astype(str)
    
    while True:
        data = df.to_dict(orient="records")
        data_json = json.dumps(data)

        if not check_tokens(data_json):
            break

        df = df.iloc[[i for i in range(len(df)) if i % 4 != 3]]

    return data_json
