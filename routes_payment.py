import base64
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from models import db, Order
from middleware import require_auth, require_admin, log_audit_event
from services.user_service import UserService
from services.sanity_service import SanityService

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
        return jsonify({'success': False, 'code': 'VALIDATION_ERROR', 'message': 'Package is required.'}), 400

    if package not in PACKAGE_PRICES:
        return jsonify({'success': False, 'code': 'INVALID_PACKAGE', 'message': 'Invalid package. Valid packages: pro, enterprise.'}), 400

    if not payment_proof:
        return jsonify({
            'success': False, 'code': 'VALIDATION_ERROR',
            'message': 'Payment proof screenshot is required. Please upload a screenshot of your successful bank transfer.'
        }), 400

    try:
        user = UserService.find_by_id(user_id)
        if not user:
            return jsonify({'success': False, 'code': 'USER_NOT_FOUND', 'message': 'User not found.'}), 404

        # Check package rank
        package_rank = {'free': 0, 'pro': 1, 'enterprise': 2}
        if package_rank.get(user.package, 0) >= package_rank.get(package, 0):
            return jsonify({
                'success': False, 'code': 'ALREADY_UPGRADED',
                'message': f'You already have the {user.package} package or higher.'
            }), 400

        # Check for existing pending request
        existing_pending = Order.query.filter_by(user_id=user_id, status='pending').first()
        if existing_pending:
            return jsonify({
                'success': False, 'code': 'PENDING_REQUEST_EXISTS',
                'message': 'You already have a pending upgrade request. Please wait for admin approval.'
            }), 400

        amount = PACKAGE_PRICES[package]

        # Upload image to Sanity
        proof_url = None
        sanity_txn_id = None
        try:
            proof_url = SanityService.upload_image(payment_proof)
            
            # Save transaction record to Sanity
            sanity_data = {
                'user_id': user_id,
                'username': user.username,
                'email': user.email,
                'package': package,
                'amount': amount,
                'currency': 'VND',
                'status': 'pending',
                'proof_image_url': proof_url,
                'created_at': datetime.utcnow().isoformat(),
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
            currency='VND',
            status='pending',
            payment_proof_url=proof_url,
            sanity_transaction_id=sanity_txn_id,
        )
        db.session.add(order)
        db.session.commit()

        log_audit_event('UPGRADE_REQUESTED', 'SUCCESS', user_id, details={
            'package': package, 'amount': amount, 'order_id': order.id,
            'has_proof': proof_url is not None,
        })

        return jsonify({
            'success': True,
            'message': 'Upgrade request submitted with payment proof. Waiting for admin approval.',
            'order': {
                'id': order.id, 'package': order.package, 'amount': order.amount,
                'currency': order.currency, 'status': order.status,
                'created_at': order.created_at.isoformat(),
            }
        }), 201

    except Exception as e:
        log_audit_event('UPGRADE_REQUESTED', 'FAILED', user_id, details={'package': package, 'error': str(e)})
        return jsonify({'success': False, 'code': 'REQUEST_FAILED', 'message': str(e)}), 500


# 2. GET USER'S REQUESTS
@payment_bp.route('/purchase/requests', methods=['GET'])
@require_auth
def get_my_requests():
    user_id = g.user.get('userId')
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    return jsonify({
        'success': True,
        'orders': [
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
        return jsonify({'success': False, 'code': 'ORDER_NOT_FOUND',
                        'message': 'Pending order not found.'}), 404

    data = request.get_json() or {}
    payment_proof = data.get('payment_proof')
    if not payment_proof:
        return jsonify({'success': False, 'code': 'VALIDATION_ERROR',
                        'message': 'payment_proof is required.'}), 400

    try:
        proof_url = SanityService.upload_image(payment_proof)
    except Exception as e:
        print(f"Sanity upload failed on re-upload: {e}. Storing base64.")
        proof_url = payment_proof

    order.payment_proof_url = proof_url
    db.session.commit()

    return jsonify({'success': True, 'message': 'Proof updated.',
                    'payment_proof_url': proof_url}), 200


# 3. GET USER PACKAGE INFO
@payment_bp.route('/purchase/package', methods=['GET'])
@require_auth
def get_package():
    user_id = g.user.get('userId')
    user = UserService.find_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'code': 'USER_NOT_FOUND', 'message': 'User not found.'}), 404

    return jsonify({
        'success': True,
        'package': {
            'package': user.package,
            'package_activated_at': user.package_activated_at.isoformat() if user.package_activated_at else None,
            'features': PACKAGE_FEATURES.get(user.package, PACKAGE_FEATURES['free']),
        }
    }), 200


# === ADMIN ENDPOINTS ===

# 4. ADMIN: GET ALL USERS
@payment_bp.route('/admin/users', methods=['GET'])
@require_auth
@require_admin
def admin_get_users():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    users, total = UserService.get_all_users(page, per_page)
    return jsonify({
        'success': True, 'users': [u.to_dict() for u in users],
        'total': total, 'page': page, 'per_page': per_page,
    }), 200


# 5. ADMIN: GET PENDING UPGRADE REQUESTS (with Sanity proof images and history)
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

    return jsonify({
        'success': True,
        'requests': result,
        'history': sanity_history,
    }), 200


# 6. ADMIN: APPROVE UPGRADE REQUEST
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

        return jsonify({
            'success': True,
            'message': f'{package.capitalize()} package approved for {user.username}.',
            'user': user.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'APPROVE_FAILED', 'message': str(e)}), 500


# 7. ADMIN: REJECT UPGRADE REQUEST
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

        return jsonify({
            'success': True,
            'message': f'Upgrade request rejected for {user.username if user else "user"}.',
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'REJECT_FAILED', 'message': str(e)}), 500