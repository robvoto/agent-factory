from __future__ import annotations

import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))


@pytest.fixture
def retailer_jsonld():
    def make(*, color="Blue", availability="https://schema.org/InStock", seller="Retailer", price="100", shipping="5", include_shipping=True):
        offer = {
            "@type": "Offer",
            "price": price,
            "priceCurrency": "USD",
            "availability": availability,
            "seller": {"@type": "Organization", "name": seller} if seller else None,
        }
        if include_shipping:
            offer["shippingDetails"] = {
                "@type": "OfferShippingDetails",
                "shippingRate": {"@type": "MonetaryAmount", "value": shipping, "currency": "USD"},
                "shippingDestination": {"@type": "DefinedRegion", "addressCountry": "US"},
            }
        return {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Camera X",
            "brand": {"@type": "Brand", "name": "Acme"},
            "model": "X-1",
            "sku": "CAM-X-BLUE",
            "color": color,
            "offers": offer,
        }

    return make
