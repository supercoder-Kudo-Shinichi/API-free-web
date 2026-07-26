import os
import json
import uuid
import requests
from config import Config
from datetime import datetime


class SanityService:
    """Service to interact with Sanity CMS for storing images and transaction history."""

    BACKUP_FILE_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'instance',
        'account_backups.json',
    )

    @staticmethod
    def _is_configured() -> bool:
        return bool(Config.SANITY_PROJECT_ID and Config.SANITY_API_TOKEN and Config.SANITY_DATASET)

    @staticmethod
    def _get_base_url():
        project_id = Config.SANITY_PROJECT_ID
        dataset = Config.SANITY_DATASET or 'production'
        api_version = getattr(Config, 'SANITY_API_VERSION', 'v2024-01-01')
        if not api_version.startswith('v'):
            api_version = f"v{api_version}"
        return f"https://{project_id}.api.sanity.io/{api_version}/data/{dataset}"

    @staticmethod
    def _load_local_backup_store() -> dict:
        if not os.path.exists(SanityService.BACKUP_FILE_PATH):
            return {}
        try:
            with open(SanityService.BACKUP_FILE_PATH, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _write_local_backup_store(store: dict) -> None:
        os.makedirs(os.path.dirname(SanityService.BACKUP_FILE_PATH), exist_ok=True)
        with open(SanityService.BACKUP_FILE_PATH, 'w', encoding='utf-8') as handle:
            json.dump(store, handle, indent=2, ensure_ascii=False)

    @staticmethod
    def _get_headers():
        return {
            "Authorization": f"Bearer {Config.SANITY_API_TOKEN}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def upload_image(base64_data: str, filename: str = None) -> str:
        """
        Upload a base64 image to Sanity Assets API and return the CDN URL.
        Correct endpoint: POST /v{version}/assets/images/{dataset}
        """
        if not Config.SANITY_PROJECT_ID or not Config.SANITY_API_TOKEN:
            raise ValueError("Sanity is not configured. Set SANITY_PROJECT_ID and SANITY_API_TOKEN.")

        if not filename:
            filename = f"payment_proof_{uuid.uuid4().hex[:8]}.png"

        # Detect mime type from data URL prefix
        mime_type = 'image/jpeg'
        if ',' in base64_data:
            header = base64_data.split(',', 1)[0]
            if 'png' in header:
                mime_type = 'image/png'
            elif 'gif' in header:
                mime_type = 'image/gif'
            elif 'webp' in header:
                mime_type = 'image/webp'
            base64_data = base64_data.split(',', 1)[1]

        import base64 as b64lib
        image_data = b64lib.b64decode(base64_data)

        project_id = Config.SANITY_PROJECT_ID
        dataset = Config.SANITY_DATASET
        api_version = getattr(Config, 'SANITY_API_VERSION', '2024-01-01')
        if api_version in ('', 'newest', None):
            api_version = '2024-01-01'

        # Correct Sanity Assets API endpoint
        upload_url = f"https://{project_id}.api.sanity.io/v{api_version}/assets/images/{dataset}"

        try:
            response = requests.post(
                upload_url,
                headers={
                    "Authorization": f"Bearer {Config.SANITY_API_TOKEN}",
                    "Content-Type": mime_type,
                },
                data=image_data,
                params={"filename": filename},
                timeout=30
            )

            print(f"[Sanity] Upload response {response.status_code}: {response.text[:300]}")

            if response.status_code in (200, 201):
                result = response.json()
                # Response has 'document' containing '_id' and 'url'
                doc = result.get('document', result)
                cdn_url = doc.get('url', '')
                if cdn_url:
                    return cdn_url
                # Build URL manually if not returned
                asset_id = doc.get('_id', '').replace('image-', '')
                if asset_id:
                    ext = filename.rsplit('.', 1)[-1] if '.' in filename else 'png'
                    return f"https://cdn.sanity.io/images/{project_id}/{dataset}/{asset_id}-{ext}"

            raise ValueError(f"Failed to upload image to Sanity (HTTP {response.status_code}): {response.text[:500]}")

        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Sanity image upload error: {str(e)}")

    @staticmethod
    def save_account_backup(account_data: dict) -> str:
        """
        Save a backup snapshot of the user's account/package data to Sanity.
        Falls back to a local JSON backup file when Sanity is unavailable.
        Returns the Sanity document ID or a local backup identifier.
        """
        doc_id = f"account-backup-{uuid.uuid4().hex[:20]}"
        doc = {
            "_id": doc_id,
            "_type": "accountBackup",
            "user_id": account_data.get("user_id"),
            "username": account_data.get("username", ""),
            "email": account_data.get("email", ""),
            "package": account_data.get("package", "free"),
            "package_activated_at": account_data.get("package_activated_at"),
            "role": account_data.get("role", "user"),
            "display_name": account_data.get("display_name"),
            "avatar_url": account_data.get("avatar_url"),
            "created_at": account_data.get("created_at", datetime.utcnow().isoformat()),
            "updated_at": account_data.get("updated_at", datetime.utcnow().isoformat()),
            "backup_source": account_data.get("backup_source", "app"),
        }

        if not SanityService._is_configured():
            store = SanityService._load_local_backup_store()
            store[account_data.get('user_id')] = doc
            SanityService._write_local_backup_store(store)
            return f"local:{doc_id}"

        try:
            url = f"{SanityService._get_base_url()}/mutate"
            payload = {"mutations": [{"create": doc}]}
            response = requests.post(url, headers=SanityService._get_headers(), json=payload)
            if response.status_code == 200:
                return doc_id
            raise ValueError(f"Failed to save account backup to Sanity: {response.text}")
        except Exception:
            store = SanityService._load_local_backup_store()
            store[account_data.get('user_id')] = doc
            SanityService._write_local_backup_store(store)
            return f"local:{doc_id}"

    @staticmethod
    def get_account_backups(user_id: str = None) -> list:
        """Fetch account backup documents from Sanity or local fallback storage.
        
        Args:
            user_id: If provided, only return backups for this specific user.
                     If None, return all backups.
        """
        if not SanityService._is_configured():
            store = SanityService._load_local_backup_store()
            if user_id:
                doc = store.get(user_id)
                return [doc] if doc else []
            return list(store.values())

        try:
            if user_id:
                groq = f'*[_type == "accountBackup" && user_id == "{user_id}"] | order(updated_at desc)'
            else:
                groq = '*[_type == "accountBackup"] | order(updated_at desc)'
            url = f"{SanityService._get_base_url()}/query"
            params = {"query": groq}
            response = requests.get(url, headers=SanityService._get_headers(), params=params)
            if response.status_code == 200:
                result = response.json()
                return result.get("result", [])
            return []
        except Exception:
            return []

    @staticmethod
    def update_account_backup(document_id: str, updates: dict):
        """Patch an existing account backup with latest values."""
        try:
            url = f"{SanityService._get_base_url()}/mutate"
            payload = {"mutations": [{"patch": {"id": document_id, "set": updates}}]}
            response = requests.post(url, headers=SanityService._get_headers(), json=payload)
            if response.status_code != 200:
                print(f"Failed to update account backup: {response.text}")
        except Exception as e:
            print(f"Sanity update account backup error: {str(e)}")

    @staticmethod
    def save_transaction(transaction_data: dict) -> str:
        """
        Save a transaction record to Sanity as a document.
        
        transaction_data should contain:
        - user_id, username, email, package, amount, status, 
          proof_image_url, approved_by, created_at
        
        Returns the Sanity document ID.
        """
        from datetime import datetime
        
        doc_id = f"transaction-{uuid.uuid4().hex[:20]}"

        doc = {
            "_id": doc_id,
            "_type": "transaction",
            "user_id": transaction_data.get("user_id"),
            "username": transaction_data.get("username", ""),
            "email": transaction_data.get("email", ""),
            "package": transaction_data.get("package"),
            "amount": transaction_data.get("amount"),
            "currency": transaction_data.get("currency", "VND"),
            "status": transaction_data.get("status", "pending"),
            "payment_method": "manual",
            "proof_image_url": transaction_data.get("proof_image_url", ""),
            "approved_by": transaction_data.get("approved_by"),
            "created_at": transaction_data.get("created_at", datetime.utcnow().isoformat()),
        }

        try:
            url = f"{SanityService._get_base_url()}/mutate"
            payload = {
                "mutations": [
                    {"create": doc}
                ]
            }
            
            response = requests.post(url, headers=SanityService._get_headers(), json=payload)
            
            if response.status_code == 200:
                return doc_id
            else:
                raise ValueError(f"Failed to save transaction to Sanity: {response.text}")
        except Exception as e:
            raise ValueError(f"Sanity save transaction error: {str(e)}")

    @staticmethod
    def get_transactions(query_params: dict = None) -> list:
        """
        Fetch transactions from Sanity using GROQ query.
        
        Returns list of transaction documents.
        """
        try:
            # GROQ query to get all transactions, ordered by creation date
            groq = '*[_type == "transaction"] | order(created_at desc)'
            
            url = f"{SanityService._get_base_url()}/query"
            params = {"query": groq}
            
            response = requests.get(
                url, 
                headers=SanityService._get_headers(),
                params=params
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("result", [])
            else:
                return []
        except Exception:
            return []

    @staticmethod
    def update_transaction_status(document_id: str, status: str, approved_by: str = None):
        """
        Update the status of a transaction document in Sanity.
        """
        try:
            url = f"{SanityService._get_base_url()}/mutate"
            
            patch_data = {
                "status": status,
            }
            if approved_by:
                patch_data["approved_by"] = approved_by

            payload = {
                "mutations": [
                    {
                        "patch": {
                            "id": document_id,
                            "set": patch_data
                        }
                    }
                ]
            }
            
            response = requests.post(url, headers=SanityService._get_headers(), json=payload)
            
            if response.status_code != 200:
                print(f"Failed to update transaction status: {response.text}")
        except Exception as e:
            print(f"Sanity update transaction error: {str(e)}")