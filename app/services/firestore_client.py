"""Firebase Admin SDK bootstrap and Firestore client singleton."""

import json
from functools import lru_cache

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.client import Client as FirestoreClient

from app.core.config import Settings, get_settings


def _load_credentials(settings: Settings) -> credentials.Certificate:
    if settings.firebase_credentials_json:
        return credentials.Certificate(json.loads(settings.firebase_credentials_json))
    return credentials.Certificate(settings.firebase_credentials_path)


@lru_cache
def get_firestore_client() -> FirestoreClient:
    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(_load_credentials(get_settings()))
    return firestore.client(app)
