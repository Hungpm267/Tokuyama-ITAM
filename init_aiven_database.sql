-- =============================================================================
-- TOKUYAMA VIETNAM - IT ASSET MANAGEMENT SYSTEM (ITAM)
-- DATABASE INITIALIZATION SCRIPT FOR POSTGRESQL (AIVEN.IO / CLOUD / ON-PREMISE)
-- =============================================================================
-- Generated automatically from SQLAlchemy 2.x & Alembic Migrations
-- Schema revision: 0002 (Head)
-- Compatible with PostgreSQL 14, 15, 16+
-- =============================================================================

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE users (
    username VARCHAR(50) NOT NULL, 
    password_hash TEXT NOT NULL, 
    display_name VARCHAR(100) NOT NULL, 
    role_id INTEGER NOT NULL, 
    preferred_lang VARCHAR(5) DEFAULT 'en' NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    last_login_at TIMESTAMP WITH TIME ZONE, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_users PRIMARY KEY (id), 
    CONSTRAINT ck_users_lang_allowed CHECK (preferred_lang IN ('en', 'ja', 'vi')), 
    CONSTRAINT ck_users_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT fk_users_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_users_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_users_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_users_is_deleted ON users (is_deleted);

CREATE UNIQUE INDEX uq_alive_users_username ON users (username) WHERE is_deleted = false;

CREATE TYPE card_type AS ENUM ('STAFF', 'CONTRACTOR', 'GUEST');

CREATE TYPE card_status AS ENUM ('IN_STOCK', 'BORROWED', 'LOST', 'DAMAGED');

CREATE TABLE access_cards (
    card_no VARCHAR(50) NOT NULL, 
    card_type card_type DEFAULT 'CONTRACTOR' NOT NULL, 
    status card_status DEFAULT 'IN_STOCK' NOT NULL, 
    note TEXT, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_access_cards PRIMARY KEY (id), 
    CONSTRAINT ck_access_cards_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT fk_access_cards_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_access_cards_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_access_cards_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_access_cards_is_deleted ON access_cards (is_deleted);

CREATE UNIQUE INDEX uq_alive_access_cards_card_no ON access_cards (card_no) WHERE is_deleted = false;

CREATE TABLE asset_categories (
    name_en VARCHAR(100) NOT NULL, 
    name_ja VARCHAR(100), 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_asset_categories PRIMARY KEY (id), 
    CONSTRAINT ck_asset_categories_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT fk_asset_categories_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_asset_categories_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_asset_categories_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_asset_categories_is_deleted ON asset_categories (is_deleted);

CREATE UNIQUE INDEX uq_alive_asset_categories_name_en ON asset_categories (name_en) WHERE is_deleted = false;

CREATE TABLE asset_tags (
    code VARCHAR(30) NOT NULL, 
    name_en VARCHAR(100) NOT NULL, 
    name_ja VARCHAR(100), 
    color VARCHAR(7), 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_asset_tags PRIMARY KEY (id), 
    CONSTRAINT ck_asset_tags_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT fk_asset_tags_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_asset_tags_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_asset_tags_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_asset_tags_is_deleted ON asset_tags (is_deleted);

CREATE UNIQUE INDEX uq_alive_asset_tags_code ON asset_tags (code) WHERE is_deleted = false;

CREATE TYPE audit_action AS ENUM ('CREATE', 'UPDATE', 'DELETE', 'RESTORE', 'LOGIN', 'LOGIN_FAIL', 'REVEAL');

CREATE TABLE audit_logs (
    id BIGSERIAL NOT NULL, 
    user_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    table_name VARCHAR(50) NOT NULL, 
    record_id INTEGER, 
    action audit_action NOT NULL, 
    before_after JSONB, 
    ip_address INET, 
    CONSTRAINT pk_audit_logs PRIMARY KEY (id), 
    CONSTRAINT fk_audit_logs_user_id FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE INDEX ix_audit_logs_table_record ON audit_logs (table_name, record_id);

CREATE INDEX ix_audit_logs_user_action ON audit_logs (user_id, action);

CREATE TYPE delivery_status AS ENUM ('PENDING', 'DELIVERED');

CREATE TABLE contracts (
    code VARCHAR(50) NOT NULL, 
    vendor_name VARCHAR(100) DEFAULT 'KDDI Vietnam', 
    signed_date DATE, 
    delivery_status delivery_status DEFAULT 'PENDING' NOT NULL, 
    note TEXT, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_contracts PRIMARY KEY (id), 
    CONSTRAINT ck_contracts_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT fk_contracts_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_contracts_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_contracts_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_contracts_is_deleted ON contracts (is_deleted);

CREATE UNIQUE INDEX uq_alive_contracts_code ON contracts (code) WHERE is_deleted = false;

CREATE TABLE departments (
    code VARCHAR(30), 
    name_en VARCHAR(100) NOT NULL, 
    name_ja VARCHAR(100), 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_departments PRIMARY KEY (id), 
    CONSTRAINT ck_departments_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT fk_departments_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_departments_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_departments_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_departments_is_deleted ON departments (is_deleted);

CREATE UNIQUE INDEX uq_alive_departments_code ON departments (code) WHERE is_deleted = false AND code IS NOT NULL;

CREATE UNIQUE INDEX uq_alive_departments_name_en ON departments (name_en) WHERE is_deleted = false;

CREATE TYPE license_type AS ENUM ('PERPETUAL', 'SUBSCRIPTION');

CREATE TABLE license_products (
    name VARCHAR(100) NOT NULL, 
    vendor VARCHAR(100), 
    license_type license_type, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_license_products PRIMARY KEY (id), 
    CONSTRAINT ck_license_products_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT fk_license_products_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_license_products_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_license_products_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_license_products_is_deleted ON license_products (is_deleted);

CREATE UNIQUE INDEX uq_alive_license_products_name ON license_products (name) WHERE is_deleted = false;

CREATE TABLE locations (
    building VARCHAR(50) NOT NULL, 
    floor VARCHAR(50) NOT NULL, 
    room_en VARCHAR(100) NOT NULL, 
    room_ja VARCHAR(100), 
    is_access_controlled BOOLEAN DEFAULT false NOT NULL, 
    description TEXT, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_locations PRIMARY KEY (id), 
    CONSTRAINT ck_locations_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT fk_locations_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_locations_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_locations_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_locations_is_deleted ON locations (is_deleted);

CREATE UNIQUE INDEX uq_alive_locations_building_floor_room_en ON locations (building, floor, room_en) WHERE is_deleted = false;

CREATE TABLE roles (
    code VARCHAR(30) NOT NULL, 
    name_en VARCHAR(100) NOT NULL, 
    name_ja VARCHAR(100), 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_roles PRIMARY KEY (id), 
    CONSTRAINT ck_roles_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT fk_roles_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_roles_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_roles_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_roles_is_deleted ON roles (is_deleted);

CREATE UNIQUE INDEX uq_alive_roles_code ON roles (code) WHERE is_deleted = false;

CREATE TABLE user_permission_overrides (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    module VARCHAR(40) NOT NULL, 
    action VARCHAR(10) NOT NULL, 
    granted BOOLEAN NOT NULL, 
    CONSTRAINT pk_user_permission_overrides PRIMARY KEY (id), 
    CONSTRAINT ck_user_permission_overrides_action_allowed CHECK (action IN ('view', 'add', 'change', 'delete')), 
    CONSTRAINT fk_user_permission_overrides_user_id FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_user_permission_overrides_user_id_module_action UNIQUE (user_id, module, action)
);

CREATE TABLE access_card_locations (
    card_id INTEGER NOT NULL, 
    location_id INTEGER NOT NULL, 
    CONSTRAINT pk_access_card_locations PRIMARY KEY (card_id, location_id), 
    CONSTRAINT fk_access_card_locations_card_id FOREIGN KEY(card_id) REFERENCES access_cards (id) ON DELETE CASCADE, 
    CONSTRAINT fk_access_card_locations_location_id FOREIGN KEY(location_id) REFERENCES locations (id) ON DELETE RESTRICT
);

CREATE TABLE contract_lines (
    contract_id INTEGER NOT NULL, 
    item_type VARCHAR(100) NOT NULL, 
    spec TEXT, 
    qty_ordered INTEGER NOT NULL, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_contract_lines PRIMARY KEY (id), 
    CONSTRAINT ck_contract_lines_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT ck_contract_lines_qty_positive CHECK (qty_ordered > 0), 
    CONSTRAINT fk_contract_lines_contract_id FOREIGN KEY(contract_id) REFERENCES contracts (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_contract_lines_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_contract_lines_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_contract_lines_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_contract_lines_is_deleted ON contract_lines (is_deleted);

CREATE TABLE licenses (
    product_id INTEGER NOT NULL, 
    license_key_enc BYTEA, 
    key_version SMALLINT DEFAULT 1 NOT NULL, 
    seats INTEGER NOT NULL, 
    start_date DATE, 
    expiry_date DATE, 
    contract_id INTEGER, 
    note TEXT, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_licenses PRIMARY KEY (id), 
    CONSTRAINT ck_licenses_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT ck_licenses_expiry_after_start CHECK (expiry_date IS NULL OR start_date IS NULL OR expiry_date >= start_date), 
    CONSTRAINT ck_licenses_seats_positive CHECK (seats > 0), 
    CONSTRAINT fk_licenses_contract_id FOREIGN KEY(contract_id) REFERENCES contracts (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_licenses_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_licenses_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_licenses_product_id FOREIGN KEY(product_id) REFERENCES license_products (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_licenses_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_licenses_is_deleted ON licenses (is_deleted);

CREATE TYPE person_status AS ENUM ('SCHEDULED', 'ACTIVE', 'RESIGNED');

CREATE TABLE persons (
    staff_code VARCHAR(50) NOT NULL, 
    user_login_id VARCHAR(50), 
    full_name VARCHAR(100) NOT NULL, 
    department_id INTEGER, 
    email VARCHAR(150), 
    status person_status DEFAULT 'ACTIVE' NOT NULL, 
    start_working_date DATE, 
    note TEXT, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_persons PRIMARY KEY (id), 
    CONSTRAINT ck_persons_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT fk_persons_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_persons_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_persons_department_id FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_persons_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_persons_full_name ON persons (full_name);

CREATE INDEX ix_persons_is_deleted ON persons (is_deleted);

CREATE UNIQUE INDEX uq_alive_persons_email ON persons (email) WHERE is_deleted = false AND email IS NOT NULL;

CREATE UNIQUE INDEX uq_alive_persons_staff_code ON persons (staff_code) WHERE is_deleted = false;

CREATE UNIQUE INDEX uq_alive_persons_user_login_id ON persons (user_login_id) WHERE is_deleted = false AND user_login_id IS NOT NULL;

CREATE TYPE phone_device_type AS ENUM ('IP_PHONE', 'DECT_STATION', 'PBX', 'WIFI_PHONE');

CREATE TABLE phones (
    device_name VARCHAR(50) NOT NULL, 
    device_type phone_device_type NOT NULL, 
    extension_number VARCHAR(10), 
    location_id INTEGER, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    remarks TEXT, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_phones PRIMARY KEY (id), 
    CONSTRAINT ck_phones_no_na_literal CHECK (extension_number IS NULL OR extension_number <> 'N/A'), 
    CONSTRAINT ck_phones_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT fk_phones_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_phones_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_phones_location_id FOREIGN KEY(location_id) REFERENCES locations (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_phones_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_phones_is_deleted ON phones (is_deleted);

CREATE UNIQUE INDEX uq_alive_phones_device_name ON phones (device_name) WHERE is_deleted = false;

CREATE UNIQUE INDEX uq_alive_phones_extension_number ON phones (extension_number) WHERE is_deleted = false AND extension_number IS NOT NULL;

CREATE TABLE role_permissions (
    id SERIAL NOT NULL, 
    role_id INTEGER NOT NULL, 
    module VARCHAR(40) NOT NULL, 
    action VARCHAR(10) NOT NULL, 
    CONSTRAINT pk_role_permissions PRIMARY KEY (id), 
    CONSTRAINT ck_role_permissions_action_allowed CHECK (action IN ('view', 'add', 'change', 'delete')), 
    CONSTRAINT fk_role_permissions_role_id FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_role_permissions_role_id_module_action UNIQUE (role_id, module, action)
);

CREATE TYPE asset_status AS ENUM ('IN_STOCK', 'IN_USE', 'REPAIR', 'DISPOSED', 'LOST');

CREATE TABLE assets (
    asset_code VARCHAR(50), 
    vendor_code VARCHAR(50), 
    category_id INTEGER NOT NULL, 
    contract_line_id INTEGER, 
    model VARCHAR(150), 
    form_factor VARCHAR(30), 
    serial VARCHAR(100), 
    hwid VARCHAR(100), 
    mac_ethernet VARCHAR(20), 
    mac_wifi VARCHAR(20), 
    status asset_status DEFAULT 'IN_STOCK' NOT NULL, 
    note TEXT, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_assets PRIMARY KEY (id), 
    CONSTRAINT ck_assets_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT ck_assets_has_some_identifier CHECK (asset_code IS NOT NULL OR vendor_code IS NOT NULL OR serial IS NOT NULL), 
    CONSTRAINT fk_assets_category_id FOREIGN KEY(category_id) REFERENCES asset_categories (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_assets_contract_line_id FOREIGN KEY(contract_line_id) REFERENCES contract_lines (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_assets_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_assets_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_assets_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_assets_hwid ON assets (hwid);

CREATE INDEX ix_assets_is_deleted ON assets (is_deleted);

CREATE INDEX ix_assets_mac_ethernet ON assets (mac_ethernet);

CREATE INDEX ix_assets_mac_wifi ON assets (mac_wifi);

CREATE UNIQUE INDEX uq_alive_assets_asset_code ON assets (asset_code) WHERE is_deleted = false AND asset_code IS NOT NULL;

CREATE UNIQUE INDEX uq_alive_assets_serial ON assets (serial) WHERE is_deleted = false AND serial IS NOT NULL;

CREATE UNIQUE INDEX uq_alive_assets_vendor_code ON assets (vendor_code) WHERE is_deleted = false AND vendor_code IS NOT NULL;

CREATE TABLE card_loans (
    card_id INTEGER NOT NULL, 
    person_id INTEGER, 
    external_name VARCHAR(100), 
    external_company VARCHAR(150), 
    purpose TEXT, 
    borrowed_at DATE NOT NULL, 
    expected_return_at DATE, 
    returned_at DATE, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_card_loans PRIMARY KEY (id), 
    CONSTRAINT ck_card_loans_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT ck_card_loans_expected_after_borrowed CHECK (expected_return_at IS NULL OR expected_return_at >= borrowed_at), 
    CONSTRAINT ck_card_loans_borrower_required CHECK (person_id IS NOT NULL OR (external_name IS NOT NULL AND length(btrim(external_name)) > 0)), 
    CONSTRAINT ck_card_loans_returned_after_borrowed CHECK (returned_at IS NULL OR returned_at >= borrowed_at), 
    CONSTRAINT fk_card_loans_card_id FOREIGN KEY(card_id) REFERENCES access_cards (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_card_loans_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_card_loans_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_card_loans_person_id FOREIGN KEY(person_id) REFERENCES persons (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_card_loans_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_card_loans_is_deleted ON card_loans (is_deleted);

CREATE UNIQUE INDEX uq_open_card_loans_card_id ON card_loans (card_id) WHERE returned_at IS NULL AND is_deleted = false;

CREATE TABLE person_secrets (
    person_id INTEGER NOT NULL, 
    pc_password_enc BYTEA, 
    pc_password_note VARCHAR(200), 
    email_password_enc BYTEA, 
    email_password_note VARCHAR(200), 
    key_version SMALLINT DEFAULT 1 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_by INTEGER, 
    CONSTRAINT pk_person_secrets PRIMARY KEY (person_id), 
    CONSTRAINT fk_person_secrets_person_id FOREIGN KEY(person_id) REFERENCES persons (id) ON DELETE CASCADE, 
    CONSTRAINT fk_person_secrets_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE TABLE asset_tag_links (
    asset_id INTEGER NOT NULL, 
    tag_id INTEGER NOT NULL, 
    CONSTRAINT pk_asset_tag_links PRIMARY KEY (asset_id, tag_id), 
    CONSTRAINT fk_asset_tag_links_asset_id FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE CASCADE, 
    CONSTRAINT fk_asset_tag_links_tag_id FOREIGN KEY(tag_id) REFERENCES asset_tags (id) ON DELETE RESTRICT
);

CREATE TABLE assignments (
    asset_id INTEGER NOT NULL, 
    person_id INTEGER NOT NULL, 
    borrowed_at DATE NOT NULL, 
    returned_at DATE, 
    note TEXT, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_assignments PRIMARY KEY (id), 
    CONSTRAINT ck_assignments_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT ck_assignments_returned_after_borrowed CHECK (returned_at IS NULL OR returned_at >= borrowed_at), 
    CONSTRAINT fk_assignments_asset_id FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_assignments_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_assignments_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_assignments_person_id FOREIGN KEY(person_id) REFERENCES persons (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_assignments_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_assignments_is_deleted ON assignments (is_deleted);

CREATE UNIQUE INDEX uq_open_assignments_asset_id ON assignments (asset_id) WHERE returned_at IS NULL AND is_deleted = false;

CREATE TABLE license_assignments (
    license_id INTEGER NOT NULL, 
    asset_id INTEGER, 
    person_id INTEGER, 
    assigned_at DATE NOT NULL, 
    expiry_date DATE, 
    removed_at DATE, 
    note TEXT, 
    id SERIAL NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by INTEGER, 
    updated_by INTEGER, 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    delete_reason VARCHAR(300), 
    deleted_by INTEGER, 
    CONSTRAINT pk_license_assignments PRIMARY KEY (id), 
    CONSTRAINT ck_license_assignments_soft_delete_coherent CHECK ((is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL) OR (is_deleted = true AND deleted_at IS NOT NULL AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)), 
    CONSTRAINT ck_license_assignments_target_required CHECK (asset_id IS NOT NULL OR person_id IS NOT NULL), 
    CONSTRAINT ck_license_assignments_removed_after_assigned CHECK (removed_at IS NULL OR removed_at >= assigned_at), 
    CONSTRAINT fk_license_assignments_asset_id FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_license_assignments_created_by FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_license_assignments_deleted_by FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_license_assignments_license_id FOREIGN KEY(license_id) REFERENCES licenses (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_license_assignments_person_id FOREIGN KEY(person_id) REFERENCES persons (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_license_assignments_updated_by FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_license_assignments_is_deleted ON license_assignments (is_deleted);

CREATE UNIQUE INDEX uq_open_license_assignments_license_id_asset_id ON license_assignments (license_id, asset_id) WHERE removed_at IS NULL AND is_deleted = false AND asset_id IS NOT NULL;

CREATE UNIQUE INDEX uq_open_license_assignments_license_id_person_id ON license_assignments (license_id, person_id) WHERE removed_at IS NULL AND is_deleted = false AND person_id IS NOT NULL;

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> 0002

CREATE OR REPLACE FUNCTION itam_audit_immutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_logs chi cho phep INSERT va SELECT (thao tac bi chan: %)',
                TG_OP
            USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_logs_no_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION itam_audit_immutable();

CREATE TRIGGER trg_audit_logs_no_delete
        BEFORE DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION itam_audit_immutable();

CREATE TRIGGER trg_audit_logs_no_truncate
        BEFORE TRUNCATE ON audit_logs
        FOR EACH STATEMENT EXECUTE FUNCTION itam_audit_immutable();

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

-- Foreign Key bổ sung cho users.role_id liên kết roles.id (do use_alter=True)
ALTER TABLE users ADD CONSTRAINT fk_users_role_id FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE RESTRICT;



-- =============================================================================
-- SEED DATA: ROLES & DEFAULT PERMISSIONS & INITIAL USERS
-- =============================================================================

-- 1. Roles
INSERT INTO roles (id, code, name_en, name_ja, created_at, updated_at, is_deleted) VALUES
(1, 'ADMIN', 'Administrator', '管理者', now(), now(), false),
(2, 'GA_MANAGER', 'GA Manager', '総務課長', now(), now(), false),
(3, 'EXECUTIVE', 'Executive', '役員', now(), now(), false)
ON CONFLICT (id) DO NOTHING;

SELECT setval('roles_id_seq', (SELECT MAX(id) FROM roles));

-- 2. Role Permissions
INSERT INTO role_permissions (role_id, module, action) VALUES
(1, 'persons', 'view'),
(1, 'persons', 'add'),
(1, 'persons', 'change'),
(1, 'persons', 'delete'),
(1, 'secrets', 'view'),
(1, 'secrets', 'add'),
(1, 'secrets', 'change'),
(1, 'secrets', 'delete'),
(1, 'assets', 'view'),
(1, 'assets', 'add'),
(1, 'assets', 'change'),
(1, 'assets', 'delete'),
(1, 'assignments', 'view'),
(1, 'assignments', 'add'),
(1, 'assignments', 'change'),
(1, 'assignments', 'delete'),
(1, 'licenses', 'view'),
(1, 'licenses', 'add'),
(1, 'licenses', 'change'),
(1, 'licenses', 'delete'),
(1, 'cards', 'view'),
(1, 'cards', 'add'),
(1, 'cards', 'change'),
(1, 'cards', 'delete'),
(1, 'contracts', 'view'),
(1, 'contracts', 'add'),
(1, 'contracts', 'change'),
(1, 'contracts', 'delete'),
(1, 'phones', 'view'),
(1, 'phones', 'add'),
(1, 'phones', 'change'),
(1, 'phones', 'delete'),
(1, 'audit', 'view'),
(1, 'audit', 'add'),
(1, 'audit', 'change'),
(1, 'audit', 'delete'),
(1, 'trash', 'view'),
(1, 'trash', 'add'),
(1, 'trash', 'change'),
(1, 'trash', 'delete'),
(1, 'users', 'view'),
(1, 'users', 'add'),
(1, 'users', 'change'),
(1, 'users', 'delete'),
(2, 'persons', 'view'),
(2, 'persons', 'add'),
(2, 'persons', 'change'),
(2, 'assets', 'view'),
(2, 'assignments', 'view'),
(2, 'cards', 'view'),
(2, 'cards', 'add'),
(2, 'cards', 'change'),
(2, 'cards', 'delete'),
(2, 'contracts', 'view'),
(2, 'phones', 'view'),
(2, 'phones', 'add'),
(2, 'phones', 'change'),
(3, 'persons', 'view'),
(3, 'assets', 'view'),
(3, 'assignments', 'view'),
(3, 'licenses', 'view'),
(3, 'cards', 'view'),
(3, 'contracts', 'view'),
(3, 'phones', 'view'),
(3, 'audit', 'view')
ON CONFLICT (role_id, module, action) DO NOTHING;

-- 3. Initial Users
-- Mật khẩu mặc định:
-- it.admin: TokuyamaAdmin2026!@#
-- ga.manager: TokuyamaGa2026!@#
-- executive: TokuyamaExec2026!@#
INSERT INTO users (id, username, password_hash, display_name, role_id, preferred_lang, is_active, created_at, updated_at, is_deleted) VALUES
(1, 'it.admin', '$argon2id$v=19$m=65536,t=3,p=4$tWds8vv6u5vfAOYjjuehcA$SjENve73oZ68Gy46OJ+skkKDfqleBaEWP6XAxOKM37g', 'IT Administrator', 1, 'vi', true, now(), now(), false),
(2, 'ga.manager', '$argon2id$v=19$m=65536,t=3,p=4$XHRtEq7a1d9MYjBmFuwJIw$DwXZdQV+Fhngno1z22k9ErVnL4mjcMNc8EL+EjPVqUM', 'Trưởng phòng GA (Tổng vụ)', 2, 'vi', true, now(), now(), false),
(3, 'executive', '$argon2id$v=19$m=65536,t=3,p=4$x9hWryYDOlOdtMx9+4jKLA$9XjvkLQjTZ7MLJPwpjc/+8QKLxupYyfQp9F6NPwivKU', 'Ban Giám Đốc (Executive)', 3, 'ja', true, now(), now(), false)
ON CONFLICT (id) DO NOTHING;

SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));

-- 4. Initial Asset Categories
INSERT INTO asset_categories (id, name_en, name_ja, created_at, updated_at, is_deleted) VALUES
(1, 'Laptop / Notebook', 'ノートパソコン', now(), now(), false),
(2, 'Desktop PC', 'デスクトップパソコン', now(), now(), false),
(3, 'Monitor / Display', '液晶モニター', now(), now(), false),
(4, 'Server Hardware', 'サーバー機器', now(), now(), false),
(5, 'Network / Switch / Router', 'ネットワーク機器', now(), now(), false),
(6, 'Printer / Copier', 'プリンター・複合機', now(), now(), false),
(7, 'Peripherals / Accessories', '周辺機器・アクセサリ', now(), now(), false)
ON CONFLICT (id) DO NOTHING;

SELECT setval('asset_categories_id_seq', (SELECT MAX(id) FROM asset_categories));

-- 5. Initial Departments
INSERT INTO departments (id, code, name_en, name_ja, created_at, updated_at, is_deleted) VALUES
(1, 'BOD', 'Board of Directors', '役員会', now(), now(), false),
(2, 'GA', 'General Affairs', '総務課', now(), now(), false),
(3, 'IT', 'Information Technology', 'IT課', now(), now(), false),
(4, 'ACC', 'Accounting & Finance', '経理課', now(), now(), false),
(5, 'PROD', 'Production & Factory', '製造部', now(), now(), false),
(6, 'QA', 'Quality Assurance', '品質保証課', now(), now(), false),
(7, 'LOG', 'Logistics & Supply', '物流課', now(), now(), false)
ON CONFLICT (id) DO NOTHING;

SELECT setval('departments_id_seq', (SELECT MAX(id) FROM departments));

-- 6. Initial Locations
INSERT INTO locations (id, building, floor, room_en, room_ja, created_at, updated_at, is_deleted) VALUES
(1, 'Main Building', '1', 'GA & Admin Office', '総務事務所', now(), now(), false),
(2, 'Main Building', '1', 'Server Room', 'サーバー室', now(), now(), false),
(3, 'Main Building', '2', 'Director Office', '役員室', now(), now(), false),
(4, 'Main Building', '2', 'Meeting Room A', '会議室A', now(), now(), false),
(5, 'Factory Plant', '1', 'Control Room', '中央制御室', now(), now(), false)
ON CONFLICT (id) DO NOTHING;

SELECT setval('locations_id_seq', (SELECT MAX(id) FROM locations));


-- Hoàn tất khởi tạo cơ sở dữ liệu
COMMIT;
