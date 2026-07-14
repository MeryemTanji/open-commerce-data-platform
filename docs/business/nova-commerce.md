# Nova Commerce

## Overview

Nova Commerce is a fictional European e-commerce retailer used as the business domain for Mercury.

The company sells modern lifestyle products through its online storefront and mobile application.

Rather than representing a real company, Nova Commerce provides the business context required to design realistic analytics engineering and data engineering solutions.

Mercury is the internal cloud-native data platform responsible for transforming operational data into trusted data products.

---

# Business Model

Nova Commerce operates as a direct-to-consumer (D2C) retailer.

Customers browse products online, place orders, complete payments, receive deliveries, and leave product reviews.

The company works with multiple third-party sellers and logistics providers across Europe.

---

# Operational Systems

Mercury integrates data from multiple operational systems.

| Business Function | Example System | Olist Dataset |
|-------------------|---------------|---------------|
| Commerce Platform | Shopify | Orders / Order Items |
| Customer Platform | CRM | Customers |
| Product Catalogue | PIM | Products |
| Payments | Stripe | Order Payments |
| Reviews | Trustpilot | Order Reviews |
| Seller Management | Seller Portal | Sellers |
| Logistics | Shipping Provider | Geolocation / Delivery |
| Reference Data | Master Data | Product Category Translation |

> In Mercury these systems are represented using publicly available datasets while maintaining realistic architectural boundaries.

---

# Business Processes

Nova Commerce's primary operational processes include:

- Customer registration
- Product management
- Order placement
- Payment processing
- Order fulfilment
- Shipping
- Customer reviews
- Seller onboarding
- Customer support

These processes generate the operational data ingested by Mercury.

---

# Business Stakeholders

Mercury supports multiple business functions.

| Stakeholder | Primary Questions |
|------------|-------------------|
| Executive Team | How is the business performing? |
| Finance | Revenue, payments, refunds |
| Operations | Deliveries and fulfilment |
| Commercial | Product performance |
| Customer Success | Reviews and customer satisfaction |
| Analytics | Trusted business datasets |

---

# Business KPIs

Mercury will support metrics including:

### Revenue

- Total Revenue
- Daily Revenue
- Average Order Value

### Customers

- Active Customers
- Customer Lifetime Value
- Repeat Purchase Rate

### Products

- Top Selling Products
- Category Revenue
- Product Ratings

### Operations

- Delivery Time
- Late Deliveries
- Order Fulfilment Rate

### Sellers

- Seller Revenue
- Seller Rating
- Average Delivery Performance

---

# Data Domains

Mercury's first implementation models the following domains:

- Customers
- Orders
- Order Items
- Products
- Sellers
- Payments
- Reviews
- Deliveries
- Geography

Each domain is modelled independently before being integrated into the canonical warehouse model.

---

# Engineering Assumptions

For the purposes of Mercury:

- Olist datasets simulate multiple operational systems.
- Each dataset is ingested independently.
- Source data is treated as immutable.
- Business transformations occur only after ingestion.
- Canonical business models are separated from source-specific schemas.

These assumptions intentionally mirror how modern commerce platforms are designed.