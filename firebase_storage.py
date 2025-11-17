from __future__ import annotations

"""Utility helpers for interacting with Firebase Cloud Storage.

The main entry-point is :pyfunc:`upload_image_to_firebase` which uploads raw
bytes to a bucket and returns a publicly accessible URL to the object.

The module is intentionally written with *lazy* initialisation – the Firebase
Admin SDK is only initialised the first time it is needed which avoids slowing
application start-up if you never call the upload function.

Environment variables expected:

FIREBASE_STORAGE_BUCKET – name of the storage bucket, e.g. ``my-project.appspot.com``.

At least one of the following variables must be provided so that the Admin SDK
can authenticate:

* ``FIREBASE_CREDENTIALS_FILE`` – path to a service-account JSON key file.
* ``FIREBASE_CREDENTIALS_JSON`` – **contents** of a service-account JSON key
  (useful when you cannot mount a file, e.g. in serverless).
* ``GOOGLE_APPLICATION_CREDENTIALS`` – standard Google credential file env
  (handled automatically by the Admin SDK).

If none are supplied the helper will raise a ``RuntimeError`` on first use.
"""

from typing import Optional
import os
import json
import tempfile
import asyncio
from functools import partial
from threading import Lock
import re

import firebase_admin
from firebase_admin import credentials, storage
import dotenv

dotenv.load_dotenv()

# Holds the singleton Firebase app instance once initialised.
_firebase_app: Optional[firebase_admin.App] = None
_firebase_app_lock = Lock()


def _initialise_firebase() -> firebase_admin.App:
    """Initialise Firebase Admin SDK lazily.

    The function attempts to obtain credentials from one of the supported
    environment variables described in the module docstring. It also requires
    ``FIREBASE_STORAGE_BUCKET`` to be set so that the default bucket can be
    configured.
    """

    global _firebase_app  # noqa: PLW0603 – module-level singleton is OK here.

    # First, check without a lock for performance. If the app is already
    # initialized, we can return it without the overhead of acquiring a lock.
    if _firebase_app is not None:
        return _firebase_app

    # If the app is not initialized, acquire a lock to ensure that only
    # one thread initializes it.
    with _firebase_app_lock:
        # Check again inside the lock to prevent a race condition where another
        # thread might have initialized the app while the current thread was
        # waiting for the lock.
        if _firebase_app is not None:
            return _firebase_app

        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")
        if not bucket_name:
            raise RuntimeError(
                "Missing FIREBASE_STORAGE_BUCKET environment variable – cannot "
                "initialise Firebase storage."
            )

        cred: credentials.Base = _load_credentials()

        _firebase_app = firebase_admin.initialize_app(cred, {"storageBucket": bucket_name})
        return _firebase_app


def _load_credentials() -> credentials.Base:
    """Load Firebase credentials using env vars as described in the docs."""

    # Preferred: explicit JSON *content* passed via env – avoids temp files in Docker
    json_content = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if json_content:
        try:
            data = json.loads(json_content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("FIREBASE_CREDENTIALS_JSON is not valid JSON") from exc

        # Write to a NamedTemporaryFile because firebase_admin expects a file path.
        tmp = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json", encoding="utf-8")
        with tmp as fp:
            json.dump(data, fp)
        return credentials.Certificate(tmp.name)

    # Fallback: path to the credentials file.
    file_path = os.getenv("FIREBASE_CREDENTIALS_FILE")
    if file_path and os.path.exists(file_path):
        return credentials.Certificate(file_path)

    # Last resort: rely on default application credentials (GAE / GCE, etc.)
    # This will look at GOOGLE_APPLICATION_CREDENTIALS automatically.
    try:
        return credentials.ApplicationDefault()
    except Exception as exc:  # pylint: disable=broad-except
        raise RuntimeError("Unable to load Firebase credentials; set the env vars as described in src/utils/firebase_storage.py docstring.") from exc


def upload_image_to_firebase(image_bytes: bytes, file_name: str, *, content_type: str = "image/png") -> str:
    """Upload raw *image_bytes* to Firebase Storage and return the public URL.

    Parameters
    ----------
    image_bytes:
        The binary payload of the image.
    file_name:
        Desired object name inside the bucket, e.g. ``"abc123.png"``.
    content_type:
        MIME type of the image. Defaults to ``"image/png"``. Set
        accordingly if you are uploading JPEGs or other formats.

    Returns
    -------
    str
        Public URL of the uploaded object.

    Raises
    ------
    RuntimeError
        If Firebase SDK could not be initialised due to missing configuration.
    Exception
        Propagates any errors raised by the underlying Firebase SDK when
        uploading/making the object public.
    """

    app = _initialise_firebase()

    bucket = storage.bucket(app=app)
    blob = bucket.blob(file_name)

    # Perform the upload.
    blob.upload_from_string(image_bytes, content_type=content_type)

    # Make the file publicly readable so that we can return a URL to the user.
    blob.make_public()

    return blob.public_url


async def upload_image_to_firebase_async(image_bytes: bytes, file_name: str, *, content_type: str = "image/png") -> str:
    """Asynchronous wrapper for upload_image_to_firebase that runs it in a separate thread."""
    loop = asyncio.get_running_loop()
    # Use to_thread to run the synchronous, blocking function in a separate thread
    # and wait for its result without blocking the main asyncio event loop.
    func = partial(upload_image_to_firebase, image_bytes, file_name, content_type=content_type)
    return await loop.run_in_executor(
        None,  # Use the default thread pool executor
        func
    )


def delete_image_from_firebase(file_url: str):
    """
    Deletes an image from Firebase Storage using its public URL.
    """
    if not file_url:
        return

    app = _initialise_firebase()
    bucket = storage.bucket(app=app)

    # Extract file name from URL.
    # The file name is the part of the path after the bucket name.
    # Example URL: https://storage.googleapis.com/your-bucket-name/path/to/your/file.jpg
    bucket_name = bucket.name
    # We use a regex to robustly find the file path after the bucket name in the URL.
    match = re.search(f"{bucket_name}/(.+?)(?=\\?|$)", file_url)
    if not match:
        # Log this situation? For now, we just ignore it.
        return

    file_name = match.group(1)
    blob = bucket.blob(file_name)

    # Check if the blob exists before trying to delete it.
    if blob.exists():
        blob.delete()


async def delete_image_from_firebase_async(file_url: str):
    """Asynchronous wrapper for delete_image_from_firebase."""
    loop = asyncio.get_running_loop()
    func = partial(delete_image_from_firebase, file_url)
    await loop.run_in_executor(None, func)


__all__ = ["upload_image_to_firebase", "upload_image_to_firebase_async", "delete_image_from_firebase_async"]
