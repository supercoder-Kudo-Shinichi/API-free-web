import os
import json
import uuid
import requests
from config import Config


class SanityService:
    """Service to interact with Sanity CMS for storing images and transaction history."""

    @staticmethod
    def _get_base_url():
        project_id = Config.SANITY_PROJECT_ID
        dataset = Config.SANITY_DATASET
        return f"https://{project_id}.api.sanity.io/v2024-01-01/data/{dataset}"

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
                print(f"Failed to fetch transactions from Sanity: {response.text}")
                return []
        except Exception as e:
            print(f"Sanity fetch transactions error: {str(e)}")
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