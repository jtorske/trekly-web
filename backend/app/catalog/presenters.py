"""Turn ORM rows into API response models."""

from decimal import Decimal

from app.catalog.specs import present_specs
from app.models.catalog import (
    CatalogCategory,
    CatalogProduct,
    CatalogProductVariant,
)
from app.models.user_gear import UserGearItem
from app.schemas.gear import (
    BrandRef,
    CapacityOut,
    CategoryRef,
    ImageOut,
    ProductDetailOut,
    ProductSummaryOut,
    SourceRef,
    UserGearItemOut,
    VariantOut,
    WeightOut,
)

KEY_SPEC_COUNT = 3


def _float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def category_ref(category: CatalogCategory) -> CategoryRef:
    top = category.parent or category
    return CategoryRef(
        slug=category.slug,
        name=category.name,
        icon_key=category.icon_key,
        top_slug=top.slug,
        top_name=top.name,
    )


def variant_out(variant: CatalogProductVariant, subcategory: str) -> VariantOut:
    return VariantOut(
        id=variant.id,
        name=variant.name,
        sku=variant.sku,
        status=variant.status,
        weight_g=_float(variant.weight_g),
        weight_basis=variant.weight_basis,
        capacity_ml=_float(variant.capacity_ml),
        specs=present_specs(subcategory, variant.specs or {}),
    )


def _approved_image(product: CatalogProduct) -> ImageOut | None:
    for image in product.images:
        if image.approved:
            return ImageOut(
                url=image.url,
                alt_text=image.alt_text,
                license=image.license,
                attribution=image.attribution,
                source_url=image.source_url,
            )
    return None


def _summary_fields(product: CatalogProduct) -> dict:
    variant_weights = [float(v.weight_g) for v in product.variants if v.weight_g is not None]
    return {
        "id": product.id,
        "brand": BrandRef(id=product.brand.id, slug=product.brand.slug, name=product.brand.name),
        "name": product.name,
        "display_name": f"{product.brand.name} {product.name}",
        "category": category_ref(product.category),
        "status": product.status,
        "weight_g": _float(product.weight_g),
        "weight_basis": product.weight_basis,
        "weight_range_g": (min(variant_weights), max(variant_weights)) if variant_weights else None,
        "capacity_ml": _float(product.capacity_ml),
        "variant_count": len(product.variants),
        "key_specs": present_specs(product.category.slug, product.specs or {})[:KEY_SPEC_COUNT],
        "image": _approved_image(product),
    }


def product_summary(product: CatalogProduct) -> ProductSummaryOut:
    return ProductSummaryOut(**_summary_fields(product))


def product_detail(product: CatalogProduct) -> ProductDetailOut:
    return ProductDetailOut(
        **_summary_fields(product),
        model_number=product.model_number,
        model_year=product.model_year,
        official_url=product.official_url,
        verified_at=product.verified_at,
        aliases=[alias.alias for alias in product.aliases],
        specs=present_specs(product.category.slug, product.specs or {}),
        variants=[variant_out(v, product.category.slug) for v in product.variants],
        sources=[
            SourceRef(name=link.source.name, url=link.source_url, verified_at=link.verified_at)
            for link in product.sources
        ],
    )


def effective_weight(item: UserGearItem) -> tuple[Decimal | None, str | None]:
    if item.weight_override_g is not None:
        return item.weight_override_g, "override"
    if item.variant is not None and item.variant.weight_g is not None:
        return item.variant.weight_g, "variant"
    if item.product is not None and item.product.weight_g is not None:
        return item.product.weight_g, "product"
    return None, None


def _manufacturer_weight(item: UserGearItem) -> tuple[Decimal | None, str | None]:
    if item.variant is not None and item.variant.weight_g is not None:
        return item.variant.weight_g, item.variant.weight_basis
    if item.product is not None and item.product.weight_g is not None:
        return item.product.weight_g, item.product.weight_basis
    return None, None


def _capacity(item: UserGearItem) -> CapacityOut:
    manufacturer = None
    manufacturer_source = None
    if item.variant is not None and item.variant.capacity_ml is not None:
        manufacturer, manufacturer_source = item.variant.capacity_ml, "variant"
    elif item.product is not None and item.product.capacity_ml is not None:
        manufacturer, manufacturer_source = item.product.capacity_ml, "product"
    if item.capacity_override_ml is not None:
        effective, source = item.capacity_override_ml, "override"
    else:
        effective, source = manufacturer, manufacturer_source
    return CapacityOut(
        effective_ml=_float(effective),
        source=source,
        manufacturer_ml=_float(manufacturer),
        override_ml=_float(item.capacity_override_ml),
    )


def gear_item_out(item: UserGearItem) -> UserGearItemOut:
    effective, source = effective_weight(item)
    manufacturer, basis = _manufacturer_weight(item)
    product = item.product
    if product is not None:
        display_name = f"{product.brand.name} {product.name}"
        if item.variant is not None:
            display_name += f" ({item.variant.name})"
        brand_name = product.brand.name
    else:
        display_name = item.custom_name or "Unnamed item"
        brand_name = item.custom_brand

    return UserGearItemOut(
        id=item.id,
        kind="catalog" if product is not None else "custom",
        display_name=display_name,
        brand_name=brand_name,
        category=category_ref(item.category),
        product=product_summary(product) if product is not None else None,
        variant=variant_out(item.variant, product.category.slug)
        if item.variant is not None and product is not None
        else None,
        custom_name=item.custom_name,
        custom_brand=item.custom_brand,
        custom_model=item.custom_model,
        quantity=item.quantity,
        weight=WeightOut(
            effective_g=_float(effective),
            source=source,
            manufacturer_g=_float(manufacturer),
            manufacturer_basis=basis,
            override_g=_float(item.weight_override_g),
            override_unit=item.weight_override_unit,
        ),
        capacity=_capacity(item),
        custom_specs=present_specs(item.category.slug, item.custom_specs or {}),
        notes=item.notes,
        condition=item.condition,
        image_path=item.image_path,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
