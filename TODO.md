# Implementation Plan - System Optimization

## ✅ Phase 1: Fix Response Format Standardization
- [x] **middleware.py**: Remove `response["data"] = payload` from `build_success_response` and `build_error_response`

## ✅ Phase 2: Standardize Payment Endpoints
- [x] **routes_payment.py**: Fix missing status code tuples, ensure consistent error responses

## ✅ Phase 3: Dashboard UI Enhancement
- [x] **dashboard.html**: Fix broken JS (createApiKey, revokeApiKey, renderApiKeys)
- [x] **dashboard.html**: Show real `revoked` status, add `last_used_at` column for API keys
- [x] **dashboard.html**: Add `redirect_url` + real `active` status columns for websites
- [x] **dashboard.css**: Reuse existing badge styles (`badge-success`, `badge-rejected`) for status indicators

