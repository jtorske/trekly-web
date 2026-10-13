"""add gear catalogue and personal gear inventory

Shared, normalized catalogue (catalog_*) written only by the ingestion
pipeline, plus user_gear_items for each user's own equipment. The DDL below
was generated from app/models/catalog.py and app/models/user_gear.py when this
migration was written and is frozen here on purpose.

Security model:
- RLS is enabled on every new table. Catalogue tables get a public read-only
  policy and no write policies, so only the backend/pipeline role (which
  bypasses RLS) can write them.
- user_gear_items: authenticated users can only see and change their own rows.
- Storage bucket gear-photos is private; users can only read, add or delete
  objects inside a folder named after their own user id.

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-10-13 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ['catalog_categories', 'catalog_brands', 'catalog_brand_aliases', 'catalog_sources', 'catalog_ingestion_runs', 'catalog_products', 'catalog_product_aliases', 'catalog_product_variants', 'catalog_product_images', 'catalog_product_sources', 'user_gear_items']

CATALOG_TABLES = [t for t in TABLES if t.startswith("catalog_")]

CREATE_TABLES = [
    """
    CREATE TABLE public.catalog_categories (
    	id UUID NOT NULL, 
    	slug TEXT NOT NULL, 
    	name TEXT NOT NULL, 
    	parent_id UUID, 
    	sort_order INTEGER NOT NULL, 
    	icon_key TEXT NOT NULL, 
    	description TEXT, 
    	PRIMARY KEY (id), 
    	UNIQUE (slug), 
    	FOREIGN KEY(parent_id) REFERENCES catalog_categories (id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE public.catalog_brands (
    	id UUID NOT NULL, 
    	slug TEXT NOT NULL, 
    	name TEXT NOT NULL, 
    	website_url TEXT, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	UNIQUE (slug)
    )
    """,
    """
    CREATE TABLE public.catalog_brand_aliases (
    	id UUID NOT NULL, 
    	brand_id UUID NOT NULL, 
    	alias TEXT NOT NULL, 
    	alias_normalized TEXT NOT NULL, 
    	PRIMARY KEY (id), 
    	FOREIGN KEY(brand_id) REFERENCES catalog_brands (id) ON DELETE CASCADE, 
    	UNIQUE (alias_normalized)
    )
    """,
    """
    CREATE TABLE public.catalog_sources (
    	id UUID NOT NULL, 
    	slug TEXT NOT NULL, 
    	name TEXT NOT NULL, 
    	kind TEXT NOT NULL, 
    	homepage_url TEXT, 
    	terms_url TEXT, 
    	terms_notes TEXT, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT catalog_sources_kind_check CHECK (kind in ('manufacturer','licensed_feed','manual')), 
    	UNIQUE (slug)
    )
    """,
    """
    CREATE TABLE public.catalog_ingestion_runs (
    	id UUID NOT NULL, 
    	source_id UUID NOT NULL, 
    	status TEXT NOT NULL, 
    	dry_run BOOLEAN NOT NULL, 
    	started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	finished_at TIMESTAMP WITH TIME ZONE, 
    	counts JSONB NOT NULL, 
    	errors JSONB NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT catalog_ingestion_runs_status_check CHECK (status in ('running','succeeded','partial','failed')), 
    	FOREIGN KEY(source_id) REFERENCES catalog_sources (id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE public.catalog_products (
    	id UUID NOT NULL, 
    	brand_id UUID NOT NULL, 
    	category_id UUID NOT NULL, 
    	slug TEXT NOT NULL, 
    	name TEXT NOT NULL, 
    	model_number TEXT, 
    	model_year TEXT, 
    	status TEXT NOT NULL, 
    	discontinued_at TIMESTAMP WITH TIME ZONE, 
    	weight_g NUMERIC(12, 3), 
    	weight_basis TEXT, 
    	capacity_ml NUMERIC(12, 1), 
    	specs JSONB NOT NULL, 
    	official_url TEXT, 
    	search_text TEXT NOT NULL, 
    	verified_at TIMESTAMP WITH TIME ZONE, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT catalog_products_brand_slug_key UNIQUE (brand_id, slug), 
    	CONSTRAINT catalog_products_status_check CHECK (status in ('active','discontinued')), 
    	CONSTRAINT catalog_products_weight_basis_check CHECK (weight_basis is null or weight_basis in ('minimum','trail','packaged','average','claimed')), 
    	CONSTRAINT catalog_products_weight_check CHECK (weight_g is null or weight_g > 0), 
    	CONSTRAINT catalog_products_capacity_check CHECK (capacity_ml is null or capacity_ml > 0), 
    	FOREIGN KEY(brand_id) REFERENCES catalog_brands (id) ON DELETE RESTRICT, 
    	FOREIGN KEY(category_id) REFERENCES catalog_categories (id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE public.catalog_product_aliases (
    	id UUID NOT NULL, 
    	product_id UUID NOT NULL, 
    	alias TEXT NOT NULL, 
    	alias_normalized TEXT NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT catalog_product_aliases_product_alias_key UNIQUE (product_id, alias_normalized), 
    	FOREIGN KEY(product_id) REFERENCES catalog_products (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE public.catalog_product_variants (
    	id UUID NOT NULL, 
    	product_id UUID NOT NULL, 
    	slug TEXT NOT NULL, 
    	name TEXT NOT NULL, 
    	sku TEXT, 
    	sort_order INTEGER NOT NULL, 
    	status TEXT NOT NULL, 
    	weight_g NUMERIC(12, 3), 
    	weight_basis TEXT, 
    	capacity_ml NUMERIC(12, 1), 
    	specs JSONB NOT NULL, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT catalog_product_variants_product_slug_key UNIQUE (product_id, slug), 
    	CONSTRAINT catalog_product_variants_status_check CHECK (status in ('active','discontinued')), 
    	CONSTRAINT catalog_product_variants_weight_basis_check CHECK (weight_basis is null or weight_basis in ('minimum','trail','packaged','average','claimed')), 
    	CONSTRAINT catalog_product_variants_weight_check CHECK (weight_g is null or weight_g > 0), 
    	CONSTRAINT catalog_product_variants_capacity_check CHECK (capacity_ml is null or capacity_ml > 0), 
    	FOREIGN KEY(product_id) REFERENCES catalog_products (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE public.catalog_product_images (
    	id UUID NOT NULL, 
    	product_id UUID NOT NULL, 
    	url TEXT NOT NULL, 
    	alt_text TEXT NOT NULL, 
    	license TEXT NOT NULL, 
    	attribution TEXT NOT NULL, 
    	source_url TEXT NOT NULL, 
    	approved BOOLEAN NOT NULL, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT catalog_product_images_product_url_key UNIQUE (product_id, url), 
    	FOREIGN KEY(product_id) REFERENCES catalog_products (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE public.catalog_product_sources (
    	id UUID NOT NULL, 
    	product_id UUID NOT NULL, 
    	source_id UUID NOT NULL, 
    	source_record_id TEXT NOT NULL, 
    	source_url TEXT, 
    	verified_at TIMESTAMP WITH TIME ZONE, 
    	content_hash TEXT NOT NULL, 
    	last_seen_run_id UUID, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT catalog_product_sources_source_record_key UNIQUE (source_id, source_record_id), 
    	FOREIGN KEY(product_id) REFERENCES catalog_products (id) ON DELETE CASCADE, 
    	FOREIGN KEY(source_id) REFERENCES catalog_sources (id) ON DELETE RESTRICT, 
    	FOREIGN KEY(last_seen_run_id) REFERENCES catalog_ingestion_runs (id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE public.user_gear_items (
    	id UUID NOT NULL, 
    	user_id UUID NOT NULL, 
    	product_id UUID, 
    	variant_id UUID, 
    	category_id UUID NOT NULL, 
    	custom_name TEXT, 
    	custom_brand TEXT, 
    	custom_model TEXT, 
    	quantity INTEGER NOT NULL, 
    	weight_override_g NUMERIC(12, 3), 
    	weight_override_unit TEXT, 
    	capacity_override_ml NUMERIC(12, 1), 
    	custom_specs JSONB NOT NULL, 
    	notes TEXT, 
    	condition TEXT, 
    	image_path TEXT, 
    	client_request_id UUID, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT user_gear_items_product_or_custom_check CHECK (product_id is not null or (custom_name is not null and length(trim(custom_name)) > 0)), 
    	CONSTRAINT user_gear_items_variant_requires_product_check CHECK (variant_id is null or product_id is not null), 
    	CONSTRAINT user_gear_items_quantity_check CHECK (quantity between 1 and 99), 
    	CONSTRAINT user_gear_items_weight_override_check CHECK (weight_override_g is null or weight_override_g >= 0), 
    	CONSTRAINT user_gear_items_weight_unit_check CHECK (weight_override_unit is null or weight_override_unit in ('g','kg','oz','lb')), 
    	CONSTRAINT user_gear_items_capacity_override_check CHECK (capacity_override_ml is null or capacity_override_ml > 0), 
    	CONSTRAINT user_gear_items_condition_check CHECK (condition is null or condition in ('new','good','worn','needs_repair','retired')), 
    	CONSTRAINT user_gear_items_client_request_key UNIQUE (user_id, client_request_id), 
    	FOREIGN KEY(product_id) REFERENCES catalog_products (id) ON DELETE RESTRICT, 
    	FOREIGN KEY(variant_id) REFERENCES catalog_product_variants (id) ON DELETE RESTRICT, 
    	FOREIGN KEY(category_id) REFERENCES catalog_categories (id) ON DELETE RESTRICT
    )
    """
]

DEFAULTS = [
    *[f"ALTER TABLE public.{t} ALTER COLUMN id SET DEFAULT gen_random_uuid()" for t in TABLES],
    "ALTER TABLE public.catalog_categories ALTER COLUMN sort_order SET DEFAULT 0",
    "ALTER TABLE public.catalog_products ALTER COLUMN status SET DEFAULT 'active'",
    "ALTER TABLE public.catalog_products ALTER COLUMN specs SET DEFAULT '{}'::jsonb",
    "ALTER TABLE public.catalog_products ALTER COLUMN search_text SET DEFAULT ''",
    "ALTER TABLE public.catalog_product_variants ALTER COLUMN status SET DEFAULT 'active'",
    "ALTER TABLE public.catalog_product_variants ALTER COLUMN specs SET DEFAULT '{}'::jsonb",
    "ALTER TABLE public.catalog_product_variants ALTER COLUMN sort_order SET DEFAULT 0",
    "ALTER TABLE public.catalog_product_images ALTER COLUMN approved SET DEFAULT false",
    "ALTER TABLE public.catalog_ingestion_runs ALTER COLUMN status SET DEFAULT 'running'",
    "ALTER TABLE public.catalog_ingestion_runs ALTER COLUMN dry_run SET DEFAULT false",
    "ALTER TABLE public.catalog_ingestion_runs ALTER COLUMN counts SET DEFAULT '{}'::jsonb",
    "ALTER TABLE public.catalog_ingestion_runs ALTER COLUMN errors SET DEFAULT '[]'::jsonb",
    "ALTER TABLE public.user_gear_items ALTER COLUMN quantity SET DEFAULT 1",
    "ALTER TABLE public.user_gear_items ALTER COLUMN custom_specs SET DEFAULT '{}'::jsonb",
    "ALTER TABLE public.user_gear_items ALTER COLUMN user_id SET DEFAULT auth.uid()",
]

INDEXES = [
    "CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions",
    "CREATE INDEX catalog_categories_parent_idx ON public.catalog_categories (parent_id)",
    "CREATE INDEX catalog_brand_aliases_brand_idx ON public.catalog_brand_aliases (brand_id)",
    "CREATE INDEX catalog_products_category_idx ON public.catalog_products (category_id)",
    "CREATE INDEX catalog_products_brand_idx ON public.catalog_products (brand_id)",
    "CREATE INDEX catalog_products_status_idx ON public.catalog_products (status)",
    "CREATE INDEX catalog_products_search_trgm_idx ON public.catalog_products "
    "USING gin (search_text extensions.gin_trgm_ops)",
    "CREATE INDEX catalog_product_aliases_product_idx ON public.catalog_product_aliases (product_id)",
    "CREATE INDEX catalog_product_variants_product_idx ON public.catalog_product_variants (product_id)",
    "CREATE INDEX catalog_product_images_product_idx ON public.catalog_product_images (product_id)",
    "CREATE INDEX catalog_product_sources_product_idx ON public.catalog_product_sources (product_id)",
    "CREATE INDEX user_gear_items_user_product_idx ON public.user_gear_items (user_id, product_id)",
    "ALTER TABLE public.user_gear_items ADD CONSTRAINT user_gear_items_user_fkey "
    "FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE",
]

OWN_FOLDER = "(storage.foldername(name))[1] = (select auth.uid())::text"


def upgrade() -> None:
    for statement in CREATE_TABLES + DEFAULTS + INDEXES:
        op.execute(statement)

    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")

    for table in CATALOG_TABLES:
        if table == "catalog_ingestion_runs":
            continue  # operational data, never exposed to clients
        op.execute(
            f'CREATE POLICY "{table}_public_read" ON public.{table} '
            "FOR SELECT TO anon, authenticated USING (true)"
        )
        op.execute(f"GRANT SELECT ON public.{table} TO anon, authenticated")
    # Unapproved (unlicensed / unreviewed) images are never visible to clients.
    op.execute(
        'CREATE POLICY "catalog_product_images_approved_only" ON public.catalog_product_images '
        "AS RESTRICTIVE FOR SELECT TO anon, authenticated USING (approved)"
    )

    own = "user_id = (select auth.uid())"
    for action, clause in (
        ("select", f"USING ({own})"),
        ("insert", f"WITH CHECK ({own})"),
        ("update", f"USING ({own}) WITH CHECK ({own})"),
        ("delete", f"USING ({own})"),
    ):
        op.execute(
            f'CREATE POLICY "user_gear_items_{action}_own" ON public.user_gear_items '
            f"FOR {action.upper()} TO authenticated {clause}"
        )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_gear_items TO authenticated")

    op.execute(
        "INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) "
        "VALUES ('gear-photos', 'gear-photos', false, 5242880, "
        "ARRAY['image/jpeg','image/png','image/webp']) ON CONFLICT (id) DO NOTHING"
    )
    for action, clause in (("select", "USING"), ("insert", "WITH CHECK"), ("delete", "USING")):
        op.execute(
            f'CREATE POLICY "gear_photos_{action}_own" ON storage.objects '
            f"FOR {action.upper()} TO authenticated {clause} "
            f"(bucket_id = 'gear-photos' AND {OWN_FOLDER})"
        )


def downgrade() -> None:
    for action in ("select", "insert", "delete"):
        op.execute(f'DROP POLICY IF EXISTS "gear_photos_{action}_own" ON storage.objects')
    # Objects must be removed through the Storage API before a bucket can be
    # deleted, so the (private, empty-by-policy) bucket is left in place.
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS public.{table}")
