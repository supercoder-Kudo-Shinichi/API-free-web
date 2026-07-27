"""
Sanity Service - Round-Robin Storage with 10 Sanity Projects.

Cơ chế:
- 10 Sanity projects được cấu hình trong .env (SANITY_PROJECT_ID1-10, ...)
- Mỗi lần upload, chọn project theo vòng tròn 1→10→1→10...
- Dùng file counter để lưu index hiện tại (tồn tại qua các lần restart)
- Nếu project hiện tại lỗi, tự động chuyển sang project tiếp theo
"""
import os
import json
import uuid
import base64 as b64lib
import requests
from config import Config
from datetime import datetime


# File lưu round-robin counter
COUNTER_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'instance',
    'sanity_round_counter.json',
)

BACKUP_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'instance',
    'account_backups.json',
)


def _get_sanity_projects():
    """Đọc tất cả Sanity projects từ Config (1-10)."""
    projects = []
    for i in range(1, 11):
        project_id = getattr(Config, f'SANITY_PROJECT_ID{i}', None) or (
            Config.SANITY_PROJECT_ID if i == 1 else None
        )
        dataset = getattr(Config, f'SANITY_DATASET{i}', None) or Config.SANITY_DATASET
        api_token = getattr(Config, f'SANITY_API_TOKEN{i}', None) or (
            Config.SANITY_API_TOKEN if i == 1 else None
        )
        api_version = getattr(Config, f'SANITY_API_VERSION{i}', None) or Config.SANITY_API_VERSION

        if project_id and api_token:
            projects.append({
                'project_id': project_id,
                'dataset': dataset,
                'api_token': api_token,
                'api_version': api_version,
            })
    return projects


def _get_current_index():
    """Đọc index hiện tại từ file counter."""
    try:
        if os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE, 'r') as f:
                data = json.load(f)
                return data.get('index', 0)
    except Exception:
        pass
    return 0


def _save_current_index(index):
    """Lưu index hiện tại vào file counter."""
    os.makedirs(os.path.dirname(COUNTER_FILE), exist_ok=True)
    try:
        with open(COUNTER_FILE, 'w') as f:
            json.dump({'index': index}, f)
    except Exception as e:
        print(f"[Sanity] Failed to save counter: {e}")


def _get_next_project():
    """Lấy project tiếp theo theo round-robin, trả về (project, new_index)."""
    projects = _get_sanity_projects()
    if not projects:
        return None, 0

    current_index = _get_current_index()
    next_index = (current_index + 1) % len(projects)
    _save_current_index(next_index)
    return projects[current_index], next_index


class SanityService:
    """Service to interact with Sanity CMS - Round-Robin across 10 projects."""

    @staticmethod
    def _is_configured() -> bool:
        return len(_get_sanity_projects()) > 0

    @staticmethod
    def _get_base_url(project):
        project_id = project['project_id']
        dataset = project['dataset']
        api_version = project.get('api_version', 'v2024-01-01')
        if not api_version.startswith('v'):
            api_version = f"v{api_version}"
        return f"https://{project_id}.api.sanity.io/{api_version}/data/{dataset}"

    @staticmethod
    def _get_headers(project):
        return {
            "Authorization": f"Bearer {project['api_token']}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _load_local_backup_store() -> dict:
        if not os.path.exists(BACKUP_FILE_PATH):
            return {}
        try:
            with open(BACKUP_FILE_PATH, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _write_local_backup_store(store: dict) -> None:
        os.makedirs(os.path.dirname(BACKUP_FILE_PATH), exist_ok=True)
        with open(BACKUP_FILE_PATH, 'w', encoding='utf-8') as handle:
            json.dump(store, handle, indent=2, ensure_ascii=False)

    @staticmethod
    def upload_image(base64_data: str, filename: str = None) -> str:
        """
        Upload image lên Sanity theo round-robin.
        Tự động thử project tiếp theo nếu project hiện tại lỗi.
        """
        projects = _get_sanity_projects()
        if not projects:
            raise ValueError("No Sanity projects configured. Set SANITY_PROJECT_ID and SANITY_API_TOKEN in .env")

        if not filename:
            filename = f"upload_{uuid.uuid4().hex[:8]}.png"

        # Detect mime type
        mime_type = 'image/jpeg'
        raw_data = base64_data
        if ',' in base64_data:
            header = base64_data.split(',', 1)[0]
            if 'png' in header:
                mime_type = 'image/png'
            elif 'gif' in header:
                mime_type = 'image/gif'
            elif 'webp' in header:
                mime_type = 'image/webp'
            raw_data = base64_data.split(',', 1)[1]

        image_data = b64lib.b64decode(raw_data)

        # Thử từng project theo round-robin, bắt đầu từ project hiện tại
        start_index = _get_current_index()
        num_projects = len(projects)
        last_error = None

        for attempt in range(num_projects):
            project_index = (start_index + attempt) % num_projects
            project = projects[project_index]

            upload_url = f"https://{project['project_id']}.api.sanity.io/v{project.get('api_version', '2024-01-01').replace('v', '')}/assets/images/{project['dataset']}"

            try:
                response = requests.post(
                    upload_url,
                    headers={
                        "Authorization": f"Bearer {project['api_token']}",
                        "Content-Type": mime_type,
                    },
                    data=image_data,
                    params={"filename": filename},
                    timeout=60
                )

                print(f"[Sanity] Attempt {attempt+1}/{num_projects} - Project {project_index+1}: {response.status_code}")

                if response.status_code in (200, 201):
                    result = response.json()
                    doc = result.get('document', result)
                    cdn_url = doc.get('url', '')
                    if cdn_url:
                        # Lưu index thành công
                        _save_current_index(project_index)
                        return cdn_url

                    # Build URL manually
                    asset_id = doc.get('_id', '').replace('image-', '')
                    if asset_id:
                        ext = filename.rsplit('.', 1)[-1] if '.' in filename else 'png'
                        cdn_url = f"https://cdn.sanity.io/images/{project['project_id']}/{project['dataset']}/{asset_id}-{ext}"
                        _save_current_index(project_index)
                        return cdn_url

                last_error = f"HTTP {response.status_code}: {response.text[:300]}"

            except Exception as e:
                last_error = str(e)
                print(f"[Sanity] Project {project_index+1} failed: {e}")

        # Tất cả đều thất bại
        raise ValueError(f"All {num_projects} Sanity projects failed. Last error: {last_error}")

    @staticmethod
    def save_account_backup(account_data: dict) -> str:
        """Save account backup - dùng project đầu tiên."""
        projects = _get_sanity_projects()
        doc_id = f"account-backup-{uuid.uuid4().hex[:20]}"

        doc = {
            "_id": doc_id,
            "_type": "accountBackup",
            "user_id": account_data.get("user_id"),
            "email": account_data.get("email", ""),
            "username": account_data.get("username", ""),
            "display_name": account_data.get("display_name"),
            "avatar_url": account_data.get("avatar_url"),
            "role": account_data.get("role", "user"),
            "package_quota": {
                "current_package": account_data.get("package", "free"),
                "package_activated_at": account_data.get("package_activated_at"),
                "used": account_data.get("package_used", 0),
                "remaining": account_data.get("package_remaining", None),
                "features": account_data.get("package_features", {})
            },
            "apikeys": account_data.get("apikeys", []),
            "websites": {
                "website_connected": account_data.get("website_domains", [])
            },
            "payment_history": {
                "history": account_data.get("payment_history", [])
            },
            "created_at": account_data.get("created_at", datetime.utcnow().isoformat()),
            "updated_at": account_data.get("updated_at", datetime.utcnow().isoformat()),
            "backup_source": account_data.get("backup_source", "app"),
        }

        email_key = (account_data.get('email') or '').lower().strip()
        storage_key = email_key or account_data.get('user_id')

        if not projects:
            store = SanityService._load_local_backup_store()
            store[storage_key] = doc
            SanityService._write_local_backup_store(store)
            return f"local:{doc_id}"

        try:
            project = projects[0]
            url = f"{SanityService._get_base_url(project)}/mutate"
            payload = {"mutations": [{"create": doc}]}
            response = requests.post(url, headers=SanityService._get_headers(project), json=payload)
            if response.status_code == 200:
                return doc_id
            raise ValueError(f"Failed: {response.text}")
        except Exception:
            store = SanityService._load_local_backup_store()
            store[storage_key] = doc
            SanityService._write_local_backup_store(store)
            return f"local:{doc_id}"

    @staticmethod
    def save_transaction(transaction_data: dict) -> str:
        """Save transaction - dùng project đầu tiên."""
        projects = _get_sanity_projects()
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

        if not projects:
            raise ValueError("No Sanity projects configured")

        try:
            project = projects[0]
            url = f"{SanityService._get_base_url(project)}/mutate"
            payload = {"mutations": [{"create": doc}]}
            response = requests.post(url, headers=SanityService._get_headers(project), json=payload)
            if response.status_code == 200:
                return doc_id
            raise ValueError(f"Failed: {response.text}")
        except Exception as e:
            raise ValueError(f"Sanity save transaction error: {str(e)}")

    @staticmethod
    def get_transactions(query_params: dict = None) -> list:
        """Fetch transactions từ project đầu tiên."""
        projects = _get_sanity_projects()
        if not projects:
            return []

        try:
            project = projects[0]
            groq = '*[_type == "transaction"] | order(created_at desc)'
            url = f"{SanityService._get_base_url(project)}/query"
            params = {"query": groq}
            response = requests.get(url, headers=SanityService._get_headers(project), params=params)
            if response.status_code == 200:
                result = response.json()
                return result.get("result", [])
            return []
        except Exception:
            return []

    @staticmethod
    def update_transaction_status(document_id: str, status: str, approved_by: str = None):
        """Update transaction status - dùng project đầu tiên."""
        projects = _get_sanity_projects()
        if not projects:
            return

        try:
            project = projects[0]
            url = f"{SanityService._get_base_url(project)}/mutate"
            patch_data = {"status": status}
            if approved_by:
                patch_data["approved_by"] = approved_by
            payload = {"mutations": [{"patch": {"id": document_id, "set": patch_data}}]}
            response = requests.post(url, headers=SanityService._get_headers(project), json=payload)
            if response.status_code != 200:
                print(f"Failed to update transaction: {response.text}")
        except Exception as e:
            print(f"Sanity update error: {e}")

    @staticmethod
    def get_account_backups(user_id: str = None, email: str = None) -> list:
        """Fetch account backups từ project đầu tiên."""
        projects = _get_sanity_projects()
        lookup_key = email.lower().strip() if email else user_id

        if not projects:
            store = SanityService._load_local_backup_store()
            doc = store.get(lookup_key)
            if doc:
                return [doc]
            if email and user_id:
                doc = store.get(user_id)
                return [doc] if doc else []
            return list(store.values())

        try:
            project = projects[0]
            if lookup_key and email:
                groq = f'*[_type == "accountBackup" && email == "{email.lower().strip()}"] | order(updated_at desc)'
            elif user_id:
                groq = f'*[_type == "accountBackup" && user_id == "{user_id}"] | order(updated_at desc)'
            else:
                groq = '*[_type == "accountBackup"] | order(updated_at desc)'
            url = f"{SanityService._get_base_url(project)}/query"
            params = {"query": groq}
            response = requests.get(url, headers=SanityService._get_headers(project), params=params)
            if response.status_code == 200:
                result = response.json()
                result_docs = result.get("result", [])
                if result_docs:
                    return result_docs
                if email and user_id:
                    groq = f'*[_type == "accountBackup" && user_id == "{user_id}"] | order(updated_at desc)'
                    params = {"query": groq}
                    response = requests.get(url, headers=SanityService._get_headers(project), params=params)
                    if response.status_code == 200:
                        result = response.json()
                        return result.get("result", [])
                return []
            return []
        except Exception:
            return []

    @staticmethod
    def update_account_backup(document_id: str, updates: dict):
        """Update account backup - dùng project đầu tiên."""
        projects = _get_sanity_projects()
        if not projects:
            return
        try:
            project = projects[0]
            url = f"{SanityService._get_base_url(project)}/mutate"
            payload = {"mutations": [{"patch": {"id": document_id, "set": updates}}]}
            response = requests.post(url, headers=SanityService._get_headers(project), json=payload)
            if response.status_code != 200:
                print(f"Failed to update backup: {response.text}")
        except Exception as e:
            print(f"Sanity update error: {e}")