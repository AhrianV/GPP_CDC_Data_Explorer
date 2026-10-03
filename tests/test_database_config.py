"""Database URLs must select actual storage, independently of the working directory."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from flask import Flask
from database import PROJECT_ROOT, configure_databases, connect_database, sqlite_path
from dataset_workspace import connect as connect_workspace
from models.user import create_users_table, create_user, get_user, update_avatar, update_last_login


class DatabaseConfigurationTests(unittest.TestCase):
    def setUp(self):
        folder = PROJECT_ROOT / 'instance' / 'tests'
        folder.mkdir(parents=True, exist_ok=True)
        self.primary = folder / (uuid4().hex + '.db')
        self.workspace = folder / (uuid4().hex + '.db')
        for path in (self.primary, self.workspace):
            self.addCleanup(lambda path=path: path.unlink(missing_ok=True))
        self.app = Flask(__name__)
        self.app.config.update(DATABASE_URL='sqlite:///' + self.primary.as_posix(),
                               WORKSPACE_DATABASE_URL='sqlite:///' + self.workspace.as_posix())

    def test_startup_reads_environment_settings(self):
        with patch.dict(os.environ, {'DATABASE_URL': self.app.config['DATABASE_URL'],
                                     'WORKSPACE_DATABASE_URL': self.app.config['WORKSPACE_DATABASE_URL']}):
            configured = Flask(__name__)
            configure_databases(configured)
        self.assertEqual(configured.config['DATABASE_URL'], self.app.config['DATABASE_URL'])
        self.assertEqual(configured.config['WORKSPACE_DATABASE_URL'], self.app.config['WORKSPACE_DATABASE_URL'])

    def test_missing_or_unsupported_configuration_fails_explicitly(self):
        for value in ('', 'postgresql://example.invalid/database', 'sqlite:///', 'sqlite:///file.db?mode=rw'):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                sqlite_path(value)
        with patch.dict(os.environ, {'DATABASE_URL': '', 'WORKSPACE_DATABASE_URL': ''}):
            with self.assertRaisesRegex(RuntimeError, 'Set DATABASE_URL'):
                configure_databases(self.app)

    def test_relative_absolute_and_encoded_paths(self):
        self.assertEqual(sqlite_path('sqlite:///instance/custom.db'), str((PROJECT_ROOT / 'instance/custom.db').resolve()))
        self.assertEqual(sqlite_path('sqlite:///' + self.primary.as_posix()), str(self.primary.resolve()))
        self.assertEqual(sqlite_path('sqlite:///instance/my%20data.db'), str((PROJECT_ROOT / 'instance/my data.db').resolve()))

    def test_user_operations_use_configured_primary_database(self):
        with self.app.app_context():
            create_users_table()
            create_user('configured-user', 'test-hash', email='student@example.com')
            user = get_user(username='configured-user')
            self.assertIsNotNone(user)
            self.assertTrue(update_avatar('green', user['user_id']))
            update_last_login('2026-09-18', user['user_id'])
            updated = get_user(user_id=user['user_id'])
            self.assertEqual(updated['avatar'], 'green')
            self.assertEqual(updated['last_login'], '2026-09-18')
        self.assertTrue(self.primary.exists())
        self.assertFalse(self.workspace.exists())

    def test_workspace_uses_separate_url_or_primary_when_omitted(self):
        with self.app.app_context():
            connection = connect_workspace()
            self.assertEqual(Path(connection.execute('PRAGMA database_list').fetchone()['file']).resolve(), self.workspace.resolve())
            connection.close()
            self.app.config.pop('WORKSPACE_DATABASE_URL')
            connection = connect_workspace()
            self.assertEqual(Path(connection.execute('PRAGMA database_list').fetchone()['file']).resolve(), self.primary.resolve())
            connection.close()

    def test_model_connection_outside_flask_context_uses_environment(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'sqlite:///' + self.primary.as_posix()}):
            connection = connect_database()
            self.assertEqual(Path(connection.execute('PRAGMA database_list').fetchone()['file']).resolve(), self.primary.resolve())
            connection.close()


if __name__ == '__main__':
    unittest.main()
