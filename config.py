import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "woodflow-secret-change-me")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "woodflow.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    EXPORT_FOLDER = os.path.join(BASE_DIR, "exports")