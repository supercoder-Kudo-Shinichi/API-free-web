import base64
import hashlib
import secrets
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, g, make_response
from models import db, Order, User, ApiKey, Website
from middleware import require_auth, require_admin, log_audit_event, build_success_response, build_error_response
from services.user_service import UserService
from services.sanity_service import SanityService
from services.token_service import TokenService

payment_bp = Blueprint('payment', __name__)

# Package definitions
PACKAGE_PRICES = {
    'pro': 29000,
    'enterprise': 99000,
}

PACKAGE_FEATURES = {
    'free': {
        'max_users': 100,
        'social_login': False,
        'session_management': False,
        'audit_logging': False,
        'priority_support': False,
    },
    'pro': {
        'max_users': 10000,
        'social_login': True,
        'session_management': True,
        'audit_logging': False,
        'priority_support': True,
    },
    'enterprise': {
        'max_users': None,
        'social_login': True,
        'session_management': True,
        'audit_logging': True,
        'priority_support': True,
    },
}


# 1. REQUEST PACKAGE UPGRADE (user uploads proof, saved to Sanity)
@payment_bp.route('/purchase/request', methods=['POST'])
@require_auth
def request_upgrade():
    """User requests a package upgrade with payment proof screenshot."""
    user_id = g.user.get('userId')
    data = request.get_json() or {}
    package = data.get('package')
    payment_proof = data.get('payment_proof')  # base64 string

    if not package:
        return jsonify(build_error_response('VALIDATION_ERROR', 'Package is required.')), 400

    if package not in PACKAGE_PRICES:
        return jsonify(build_error_response('INVALID_PACKAGE', 'Invalid package. Valid packages: pro, enterprise.')), 400

    if not payment_proof:
        return jsonify(build_error_response(
            'VALIDATION_ERROR',
            'Payment proof screenshot is required. Please upload a screenshot of your successful bank transfer.'
        )), 400

    try:
        user = UserService.find_by_id(user_id)
        if not user:
            return jsonify(build_error_response("USER_NOT_FOUND", "User not found.")), 404

        # Check package rank
        package_rank = {"free": 0, "pro": 1, "enterprise": 2}
        if package_rank.get(user.package, 0) >= package_rank.get(package, 0):
            return jsonify(build_error_response(
                "ALREADY_UPGRADED",
                f"You already have the {user.package} package or higher."
            )), 400

        # Check for existing pending request
        existing_pending = Order.query.filter_by(user_id=user_id, status="pending").first()
        if existing_pending:
            return jsonify(build_error_response(
                "PENDING_REQUEST_EXISTS",
                "You already have a pending upgrade request. Please wait for admin approval."
            )), 400

        amount = PACKAGE_PRICES[package]

        # Upload image to Sanity
        proof_url = None
        sanity_txn_id = None
        try:
            proof_url = SanityService.upload_image(payment_proof)
            
            # Save transaction record to Sanity
            sanity_data = {
                "user_id": user_id,
                "username": user.username,
                "email": user.email,
                "package": package,
                "amount": amount,
                "currency": "VND",
                "status": "pending",
                "proof_image_url": proof_url,
                "created_at": datetime.utcnow().isoformat(),
            }
            sanity_txn_id = SanityService.save_transaction(sanity_data)
        except Exception as e:
            # If Sanity fails, fallback to storing base64 image data directly in db
            print(f"Sanity upload failed: {str(e)}. Falling back to base64 URL.")
            proof_url = payment_proof

        order = Order(
            user_id=user_id,
            package=package,
            amount=amount,
            currency="VND",
            status="pending",
            payment_proof_url=proof_url,
            sanity_transaction_id=sanity_txn_id,
        )
        db.session.add(order)
        db.session.commit()

        log_audit_event("UPGRADE_REQUESTED", "SUCCESS", user_id, details={
            "package": package, "amount": amount, "order_id": order.id,
            "has_proof": proof_url is not None,
        })

        return jsonify(build_success_response(
            message='Upgrade request submitted with payment proof. Waiting for admin approval.',
            order={
                'id': order.id, 'package': order.package, 'amount': order.amount,
                'currency': order.currency, 'status': order.status,
                'created_at': order.created_at.isoformat(),
            }
        )), 201

    except Exception as e:
        log_audit_event("UPGRADE_REQUESTED", "FAILED", user_id, details={"package": package, "error": str(e)})
        return jsonify(build_error_response("REQUEST_FAILED", str(e))), 500


# 2. GET USER'S REQUESTS
@payment_bp.route('/purchase/requests', methods=['GET'])
@require_auth
def get_my_requests():
    user_id = g.user.get('userId')
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    return jsonify(build_success_response(
        message='Purchase history loaded.',
        orders=[
            {
                'id': o.id,
                'package': o.package,
                'amount': o.amount,
                'currency': o.currency,
                'status': o.status,
                'has_proof': o.payment_proof_url is not None,
                'payment_proof_url': o.payment_proof_url,
                'created_at': o.created_at.isoformat(),
            }
            for o in orders
        ]
    }), 200


# 2b. UPDATE PROOF for an existing pending order
@payment_bp.route('/purchase/request/<order_id>/proof', methods=['POST'])
@require_auth
def update_proof(order_id):
    """Allow user to upload/re-upload payment proof for their pending order."""
    user_id = g.user.get('userId')
    order = Order.query.filter_by(id=order_id, user_id=user_id, status='pending').first()
    if not order:
        return jsonify(build_error_response('ORDER_NOT_FOUND', 'Pending order not found.')), 404

    data = request.get_json() or {}
    payment_proof = data.get('payment_proof')
    if not payment_proof:
        return jsonify(build_error_response('VALIDATION_ERROR', 'payment_proof is required.')), 400

    try:
        proof_url = SanityService.upload_image(payment_proof)
    except Exception as e:
        print(f"Sanity upload failed on re-upload: {e}. Storing base64.")
        proof_url = payment_proof

    order.payment_proof_url = proof_url
    db.session.commit()

    return jsonify(build_success_response(message='Proof updated.', payment_proof_url=proof_url)), 200


# 3. GET USER PACKAGE INFO
@payment_bp.route('/purchase/package', methods=['GET'])
@require_auth
def get_package():
    user_id = g.user.get('userId')
    user = UserService.find_by_id(user_id)
    if not user:
        return jsonify(build_error_response('USER_NOT_FOUND', 'User not found.')), 404

    return jsonify(build_success_response(
        message='Package info loaded.',
        package={
            'package': user.package,
            'package_activated_at': user.package_activated_at.isoformat() if user.package_activated_at else None,
            'features': PACKAGE_FEATURES.get(user.package, PACKAGE_FEATURES['free']),
        }
    )), 200


# 3b. GET PACKAGE USAGE FOR CURRENT USER
@payment_bp.route('/package/usage', methods=['GET'])
@require_auth
def get_package_usage():
    user_id = g.user.get('userId')
    user = UserService.find_by_id(user_id)
    if not user:
        return jsonify(build_error_response('USER_NOT_FOUND', 'User not found.')), 404

    limit = UserService.get_package_limit(user.package)
    used = User.query.filter_by(package=user.package).count()
    remaining = None if limit is None else max(limit - used, 0)
    return jsonify(build_success_response(
        message='Package usage loaded.',
        package={
            'package': user.package,
            'used': used,
            'limit': limit,
            'remaining': remaining,
            'features': PACKAGE_FEATURES.get(user.package, PACKAGE_FEATURES['free']),
        }
    )), 200


# 3c. CREATE / LIST API KEYS
@payment_bp.route('/keys', methods=['GET'])
@require_auth
def list_api_keys():
    user_id = g.user.get('userId')
    # Show ALL keys (including revoked) so the frontend can render real status
    keys = ApiKey.query.filter_by(user_id=user_id).order_by(ApiKey.created_at.desc()).all()
    return jsonify(build_success_response(message='API keys loaded.', keys=[k.to_dict() for k in keys])), 200


@payment_bp.route('/keys', methods=['POST'])
@require_auth
def create_api_key():
    user_id = g.user.get('userId')
    data = request.get_json() or {}
    name = (data.get('name') or '').strip() or 'Integration Key'

    raw_key = f"ak_live_{secrets.token_urlsafe(24)}"
    key_hash = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()
    api_key = ApiKey(user_id=user_id, name=name, prefix='ak_live_', key_hash=key_hash)
    db.session.add(api_key)
    db.session.commit()

    return jsonify(build_success_response(
        message='API key created successfully.',
        key=raw_key,
        api_key=api_key.to_dict(),
    )), 201


@payment_bp.route('/keys/<key_id>', methods=['DELETE'])
@require_auth
def revoke_api_key(key_id):
    user_id = g.user.get('userId')
    api_key = ApiKey.query.filter_by(id=key_id, user_id=user_id).first()
    if not api_key:
        return jsonify(build_error_response('KEY_NOT_FOUND', 'API key not found.')), 404

    api_key.revoked = True
    db.session.commit()
    return jsonify(build_success_response(message='API key revoked.', api_key=api_key.to_dict())), 200


# 3d. LIST / CREATE WEBSITES
@payment_bp.route('/websites', methods=['GET'])
@require_auth
def list_websites():
    user_id = g.user.get('userId')
    websites = Website.query.filter_by(user_id=user_id, active=True).order_by(Website.created_at.desc()).all()
    return jsonify(build_success_response(message='Websites loaded.', websites=[w.to_dict() for w in websites])), 200


@payment_bp.route('/websites', methods=['POST'])
@require_auth
def create_website():
    user_id = g.user.get('userId')
    data = request.get_json() or {}
    name = (data.get('name') or '').strip() or 'New Website'
    domain = (data.get('domain') or '').strip()
    redirect_url = (data.get('redirect_url') or '').strip() or None

    if not domain:
        return jsonify(build_error_response('VALIDATION_ERROR', 'Domain is required.')), 400

    website = Website(user_id=user_id, name=name, domain=domain, redirect_url=redirect_url)
    db.session.add(website)
    db.session.commit()

    return jsonify(build_success_response(message='Website connected successfully.', website=website.to_dict())), 201


@payment_bp.route('/integrations/verify', methods=['POST'])
def verify_external_token():
    api_key_value = request.headers.get('X-API-Key') or request.headers.get('Authorization', '').replace('Bearer ', '', 1).strip()
    if not api_key_value:
        return jsonify(build_error_response('MISSING_API_KEY', 'X-API-Key header is required.')), 400

    api_key_hash = hashlib.sha256(api_key_value.encode('utf-8')).hexdigest()
    api_key = ApiKey.query.filter_by(key_hash=api_key_hash, revoked=False).first()
    if not api_key:
        return jsonify(build_error_response('INVALID_API_KEY', 'API key is invalid or revoked.')), 401

    data = request.get_json(silent=True) or {}
    token = (
        data.get('accessToken')
        or data.get('access_token')
        or data.get('token')
        or request.headers.get('Authorization', '').replace('Bearer ', '', 1).strip()
    )
    if not token:
        return jsonify(build_error_response('VALIDATION_ERROR', 'accessToken is required.')), 400

    try:
        payload = TokenService.verify_access_token(token)
        user = UserService.find_by_id(payload.get('userId'))
        if not user:
            raise ValueError('User not found.')

        expires_at = payload.get('exp')
        if isinstance(expires_at, (int, float)):
            expires_at = datetime.fromtimestamp(expires_at).isoformat()

        api_key.last_used_at = datetime.utcnow()
        db.session.commit()
        return jsonify(build_success_response(
            message='Access token is valid.',
            valid=True,
            tokenType='access',
            expiresAt=expires_at,
            user=user.to_dict(),
        )), 200
    except Exception as e:
        return jsonify(build_error_response('TOKEN_INVALID', str(e), valid=False)), 401


# === ADMIN ENDPOINTS ===

# 4. ADMIN: GET ALL USERS
@payment_bp.route('/admin/users', methods=['GET'])
@require_auth
@require_admin
def admin_get_users():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    users, total = UserService.get_all_users(page, per_page)
    return jsonify(build_success_response(message='Users loaded.', users=[u.to_dict() for u in users], total=total, page=page, per_page=per_page)), 200


# 5. ADMIN: GET PACKAGE USAGE SUMMARY
@payment_bp.route('/admin/package-usage', methods=['GET'])
@require_auth
@require_admin
def admin_package_usage():
    summary = []
    for package_name in ['free', 'pro', 'enterprise']:
        limit = UserService.get_package_limit(package_name)
        used = User.query.filter_by(package=package_name).count()
        summary.append({
            'package': package_name,
            'used': used,
            'limit': limit,
            'remaining': None if limit is None else max(limit - used, 0),
        })
    return jsonify(build_success_response(message='Package usage summary loaded.', packages=summary)), 200


# 6. ADMIN: GET PENDING UPGRADE REQUESTS (with Sanity proof images and history)
@payment_bp.route('/admin/pending-requests', methods=['GET'])
@require_auth
@require_admin
def admin_get_pending():
    requests_list = UserService.get_pending_requests()
    result = []
    for req in requests_list:
        user = UserService.find_by_id(req.user_id)
        result.append({
            'id': req.id,
            'user_id': req.user_id,
            'username': user.username if user else 'Unknown',
            'email': user.email if user else 'Unknown',
            'package': req.package,
            'amount': req.amount,
            'currency': req.currency,
            'status': req.status,
            'payment_proof_url': req.payment_proof_url,  # Sanity CDN URL
            'sanity_transaction_id': req.sanity_transaction_id,
            'created_at': req.created_at.isoformat(),
        })

    # Also fetch history from Sanity
    sanity_history = []
    try:
        sanity_history = SanityService.get_transactions()
    except Exception as e:
        print(f"Failed to fetch Sanity history: {e}")

    return jsonify(build_success_response(message='Pending requests loaded.', requests=result, history=sanity_history)), 200


# 7. ADMIN: APPROVE UPGRADE REQUEST
@payment_bp.route('/admin/approve/<user_id>', methods=['POST'])
@require_auth
@require_admin
def admin_approve(user_id):
    admin_id = g.user.get('userId')
    data = request.get_json() or {}
    package = data.get('package', 'pro')

    try:
        order = Order.query.filter_by(user_id=user_id, status='pending').first()
        if order:
            order.status = 'approved'
            order.admin_id = admin_id
            order.reviewed_at = datetime.utcnow()

        user = UserService.approve_package(user_id, package, admin_id)
        db.session.commit()

        # Update Sanity transaction status
        if order and order.sanity_transaction_id:
            try:
                SanityService.update_transaction_status(
                    order.sanity_transaction_id, 'approved', admin_id
                )
            except Exception as e:
                print(f"Failed to update Sanity transaction: {e}")

        return jsonify(build_success_response(message=f'{package.capitalize()} package approved for {user.username}.', user=user.to_dict())), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(build_error_response('REQUEST_FAILED', str(e))), 500


# 8. ADMIN: REJECT UPGRADE REQUEST
@payment_bp.route('/admin/reject/<user_id>', methods=['POST'])
@require_auth
@require_admin
def admin_reject(user_id):
    admin_id = g.user.get('userId')

    try:
        order = Order.query.filter_by(user_id=user_id, status='pending').first()
        if order:
            order.status = 'rejected'
            order.admin_id = admin_id
            order.reviewed_at = datetime.utcnow()
            db.session.commit()

        # Update Sanity transaction status
        if order and order.sanity_transaction_id:
            try:
                SanityService.update_transaction_status(
                    order.sanity_transaction_id, 'rejected', admin_id
                )
            except Exception as e:
                print(f"Failed to update Sanity transaction: {e}")

        user = UserService.find_by_id(user_id)
        UserService.reject_package(user_id, admin_id)

        return jsonify(build_success_response(message=f'Upgrade request rejected for {user.username if user else "user"}.')), 200
    except Exception as e:
        db.session.rollback()
        return jsonify(build_error_response('REJECT_FAILED', str(e))), 500