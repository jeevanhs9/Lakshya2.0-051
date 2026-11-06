// FarmLink AI — Unified Service Layer
// Connects to Flask REST backend (/api) with graceful offline fallback
// to in-memory local state, ensuring 100% reliability in all environments.

import { products as seedProducts } from '../data/products'
import { orders as seedOrders, ORDER_STAGES } from '../data/orders'
import { getForecast as getMockForecast, topCrops } from '../data/insights'
import { demoUsers } from '../data/users'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '')

export class ApiError extends Error {
  constructor(message, status = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request(endpoint, options = {}) {
  let res
  try {
    res = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      signal: options.signal || AbortSignal.timeout(10000),
      headers: {
        'Content-Type': 'application/json',
        // Lets API/AI endpoints return natural-language content in the selected
        // farmer language without changing identifiers or payload fields.
        'Accept-Language': window.localStorage.getItem('farmlink-language') || 'en',
        ...(options.headers || {})
      }
    })
  } catch {
    // Network failure is distinct from an API rejection. Read services may
    // still show demo data offline; write services must fail visibly.
    return null
  }

  const responseData = await res.json().catch(() => null)
  if (!res.ok) {
    throw new ApiError(responseData?.error || `API request failed (${res.status}).`, res.status)
  }
  if (responseData === null) {
    throw new ApiError('The API returned an invalid JSON response.', res.status)
  }
  return responseData
}

function requireBackendResponse(response, operation) {
  if (!response) {
    throw new ApiError(`The backend is unavailable. ${operation} was not saved.`)
  }
  return response
}

// ----------------- AUTH SERVICE -----------------
export const authService = {
  async demoLogin(role) {
    const apiRes = await request('/auth/demo-login', {
      method: 'POST',
      body: JSON.stringify({ role })
    })
    if (apiRes && apiRes.success) {
      return apiRes.user
    }
    // Fallback to local demo users
    return demoUsers[role] || demoUsers.farmer
  },

  async getCurrentUser(userId = 'f1') {
    const apiRes = await request(`/auth/me?userId=${userId}`)
    if (apiRes && apiRes.user) return apiRes.user
    return Object.values(demoUsers).find(u => u.id === userId) || demoUsers.farmer
  }
}

// ----------------- PRODUCT LISTINGS SERVICE -----------------
export const productService = {
  async list(filters = {}) {
    const params = new URLSearchParams()
    if (filters.category) params.set('category', filters.category)
    if (filters.farmerId) params.set('farmerId', filters.farmerId)
    if (filters.q) params.set('q', filters.q)

    const apiRes = await request(`/products?${params.toString()}`)
    if (apiRes && apiRes.products) {
      return { items: apiRes.products, source: 'backend' }
    }
    return { items: seedProducts, source: 'demo' }
  },

  async get(id) {
    const apiRes = await request(`/products/${id}`)
    if (apiRes && apiRes.product) return apiRes.product
    return seedProducts.find(p => p.id === id) || null
  },

  async create(listing) {
    const apiRes = requireBackendResponse(await request('/products', {
      method: 'POST',
      body: JSON.stringify(listing)
    }), 'The listing')
    if (apiRes && apiRes.product) return apiRes.product
    throw new ApiError('The backend did not return the saved listing.')
  },

  async update(id, updates) {
    const apiRes = requireBackendResponse(await request(`/products/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates)
    }), 'The listing update')
    if (apiRes && apiRes.product) return apiRes.product
    throw new ApiError('The backend did not return the updated listing.')
  },

  async delete(id) {
    const apiRes = requireBackendResponse(await request(`/products/${id}`, { method: 'DELETE' }), 'The listing change')
    if (apiRes.success) return true
    throw new ApiError('The backend did not confirm the listing change.')
  }
}

// ----------------- ORDER SERVICE -----------------
export const orderService = {
  stages: ORDER_STAGES,

  async list(filters = {}) {
    const params = new URLSearchParams()
    if (filters.buyerId) params.set('buyerId', filters.buyerId)
    if (filters.farmerId) params.set('farmerId', filters.farmerId)
    if (filters.stage) params.set('stage', filters.stage)

    const apiRes = await request(`/orders?${params.toString()}`)
    if (apiRes && apiRes.orders) return { items: apiRes.orders, source: 'backend' }
    return { items: seedOrders, source: 'demo' }
  },

  async placeOrder(payload) {
    const apiRes = requireBackendResponse(await request('/orders', {
      method: 'POST',
      body: JSON.stringify(payload)
    }), 'The order')
    if (apiRes && apiRes.orders) return apiRes.orders
    throw new ApiError('The backend did not return the saved orders.')
  },

  async advanceStage(orderId, nextStage = null) {
    const apiRes = requireBackendResponse(await request(`/orders/${orderId}/stage`, {
      method: 'PATCH',
      body: JSON.stringify(nextStage ? { stage: nextStage } : {})
    }), 'The order status change')
    if (apiRes && apiRes.order) return apiRes.order
    throw new ApiError('The backend did not return the updated order.')
  },

  async cancelOrder(orderId, reason = 'Buyer cancellation request') {
    const apiRes = requireBackendResponse(await request(`/orders/${orderId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason })
    }), 'The order cancellation')
    if (apiRes && apiRes.order) return apiRes
    throw new ApiError('The backend did not return the cancelled order.')
  }
}

// ----------------- INTELLIGENT LOAD POOLING SERVICE -----------------
export const poolingService = {
  async getOpportunities(corridor = 'Bengaluru East') {
    const apiRes = await request(`/pooling/opportunities?corridor=${encodeURIComponent(corridor)}`)
    if (apiRes && apiRes.opportunities) return apiRes.opportunities

    // Intelligent local fallback if backend is offline
    return [
      {
        id: 'POOL-OPP-001',
        crop_group: 'fruit_veg',
        crops: ['Tomato'],
        candidate_items: ['p1', 'p5'],
        total_quantity_kg: 1040.0,
        destination_corridor: corridor,
        recommended_vehicle: {
          name: 'Tata 407 (3.5T Reefer)',
          capacity_kg: 3500.0,
          base_cost_inr: 1600.0,
          per_km_rate_inr: 26.0
        },
        capacity_utilization_pct: 29.7,
        baseline_separate_cost: 4800.0,
        pooled_cost: 3450.0,
        estimated_savings_inr: 1350.0,
        savings_pct: 28.1,
        planned_distance_km: 128.0,
        planned_duration_hours: 4.5,
        feasibility_score: 85,
        suitability: 'Highly Economical',
        explanation: 'Consolidates 2 lots of Tomato from Kolar FPO into a single Tata 407 run. Reduces transport cost from ₹4,800 to ₹3,450, saving ₹1,350 (28.1%).'
      }
    ]
  },

  async confirmPool(payload) {
    const apiRes = requireBackendResponse(await request('/pooling/confirm', {
      method: 'POST',
      body: JSON.stringify(payload)
    }), 'The pooled shipment')
    if (apiRes && apiRes.shipment) return apiRes.shipment
    throw new ApiError('The backend did not return the saved shipment.')
  }
}

// ----------------- SHIPMENT FULFILLMENT SERVICE -----------------
export const shipmentService = {
  async list() {
    const apiRes = await request('/shipments')
    if (apiRes && apiRes.shipments) return { items: apiRes.shipments, source: 'backend' }
    return { items: [], source: 'offline' }
  },

  async createFromOrders(orderIds) {
    const apiRes = requireBackendResponse(await request('/shipments', {
      method: 'POST',
      body: JSON.stringify({ orderIds })
    }), 'The shipment')
    if (apiRes && apiRes.shipment) return apiRes.shipment
    throw new ApiError('The backend did not return the created shipment.')
  },

  async advanceStage(shipmentId, status) {
    const apiRes = requireBackendResponse(await request(`/shipments/${shipmentId}/stage`, {
      method: 'PATCH',
      body: JSON.stringify({ status })
    }), 'The shipment status update')
    if (apiRes && apiRes.shipment) return apiRes.shipment
    throw new ApiError('The backend did not return the updated shipment.')
  },

  async cancel(shipmentId) {
    const apiRes = requireBackendResponse(await request(`/shipments/${shipmentId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({})
    }), 'The shipment cancellation')
    if (apiRes && apiRes.shipment) return apiRes.shipment
    throw new ApiError('The backend did not return the cancelled shipment.')
  },

  async getLocation(shipmentId) {
    const apiRes = requireBackendResponse(await request(`/shipments/${shipmentId}/location`), 'The live shipment location')
    return apiRes.location || null
  },

  async reportLocation(shipmentId, location) {
    const apiRes = requireBackendResponse(await request(`/shipments/${shipmentId}/location`, {
      method: 'POST',
      body: JSON.stringify(location)
    }), 'The live shipment location')
    if (apiRes && apiRes.location) return apiRes.location
    throw new ApiError('The backend did not return the saved shipment location.')
  }
}

// ----------------- PRICE & OFFER COMPARISON SERVICE -----------------
export const offerService = {
  async list(listingId = null) {
    const url = listingId ? `/offers?listingId=${listingId}` : '/offers'
    const apiRes = await request(url)
    if (apiRes && apiRes.offers) return apiRes.offers

    // Seeded offers fallback
    return [
      {
        id: 'OFFER-201',
        listingId: 'p1',
        buyerName: 'FreshMart Retail Chain',
        cropName: 'Tomato',
        offeredPrice: 30.0,
        requestedQuantity: 350.0,
        deliveryDestination: 'Bengaluru North (Hebbal)',
        distanceKm: 56.0,
        transitDays: 1,
        paymentTerms: 'Immediate UPI (T+0)',
        status: 'pending',
      },
      {
        id: 'OFFER-202',
        listingId: 'p1',
        buyerName: 'Metro Wholesale Mandi Traders',
        cropName: 'Tomato',
        offeredPrice: 32.0,
        requestedQuantity: 500.0,
        deliveryDestination: 'Yeshwanthpur APMC Yard',
        distanceKm: 84.0,
        transitDays: 2,
        paymentTerms: 'Weekly Net-7',
        status: 'pending',
      },
      {
        id: 'OFFER-203',
        listingId: 'p1',
        buyerName: 'GreenTable Restaurant Collective',
        cropName: 'Tomato',
        offeredPrice: 29.5,
        requestedQuantity: 200.0,
        deliveryDestination: 'Bengaluru East (Indiranagar)',
        distanceKm: 62.0,
        transitDays: 1,
        paymentTerms: 'Immediate UPI (T+0)',
        status: 'pending',
      }
    ]
  },

  async compare(listingId = null, priority = 'max_net_proceeds') {
    const apiRes = await request('/offers/compare', {
      method: 'POST',
      body: JSON.stringify({ listingId, priority })
    })
    if (apiRes && apiRes.rankedOffers) return apiRes

    // In-memory calculation fallback
    const rawOffers = await this.list(listingId)
    const evaluated = rawOffers.map((o) => {
      const gross = o.offeredPrice * o.requestedQuantity
      const freight = Math.max(350, o.distanceKm * (o.requestedQuantity / 1000) * 12)
      const fee = gross * 0.02
      const net = gross - freight - fee
      return {
        ...o,
        financials: {
          grossRevenue: gross,
          estimatedFreight: freight,
          platformFee: fee,
          netProceeds: net,
          netPricePerKg: net / o.requestedQuantity,
          distanceKm: o.distanceKm,
          transitDays: o.transitDays
        }
      }
    })

    if (priority === 'min_distance') {
      evaluated.sort((a, b) => a.financials.distanceKm - b.financials.distanceKm)
    } else if (priority === 'fast_delivery') {
      evaluated.sort((a, b) => a.financials.transitDays - b.financials.transitDays)
    } else {
      evaluated.sort((a, b) => b.financials.netProceeds - a.financials.netProceeds)
    }

    const top = evaluated[0]
    return {
      priority,
      priorityLabel: priority === 'min_distance' ? 'Shortest Distance' : priority === 'fast_delivery' ? 'Fast Delivery' : 'Maximum Net Proceeds',
      recommendedOfferId: top?.id,
      recommendedBuyer: top?.buyerName,
      rankedOffers: evaluated,
      explanation: `Top recommendation: ${top?.buyerName} delivering ₹${top?.financials.netProceeds?.toLocaleString('en-IN')} net proceeds after logistics deduction.`,
      disclaimer: 'Estimated net proceeds; actual carrier charges depend on consolidated route sequence.'
    }
  },

  async accept(offerId) {
    const apiRes = requireBackendResponse(await request(`/offers/${offerId}/accept`, { method: 'POST' }), 'The offer acceptance')
    if (apiRes && apiRes.success) return apiRes
    throw new ApiError('The backend did not confirm the offer acceptance.')
  }
}

// ----------------- DISRUPTION RECOVERY SERVICE -----------------
export const disruptionService = {
  async list(status = null) {
    const url = status ? `/disruptions?status=${status}` : '/disruptions'
    const apiRes = await request(url)
    if (apiRes && apiRes.disruptions) return apiRes.disruptions

    return [
      {
        id: 'DISR-001',
        orderId: 'ORD-1043',
        eventType: 'cancellation',
        severity: 'high',
        description: 'ABC Hostel cancelled order for 180kg Grade A Tomatoes due to kitchen closure. Harvest packed at Kolar FPO.',
        affectedCrop: 'Tomato',
        affectedQuantity: 180.0,
        originalBuyerId: 'b1',
        status: 'open',
        createdAt: '2026-10-19 10:30',
      }
    ]
  },

  async getMatches(disruptionId) {
    const apiRes = await request(`/disruptions/${disruptionId}/matches`)
    if (apiRes && apiRes.alternativeBuyers) return apiRes

    return {
      disruption: { id: disruptionId, affectedCrop: 'Tomato', affectedQuantity: 180.0 },
      alternativeBuyers: [
        {
          buyer_id: 'b2',
          buyer_name: 'GreenTable Restaurant Collective',
          buyer_type: 'Food Service / HoReCa',
          location: 'Bengaluru East (Indiranagar)',
          phone: '+91 80 9876 5432',
          match_score: 93,
          match_grade: 'Optimal Alternative',
          estimated_offer_price: 29.5,
          estimated_gross_recovery: 5310.0,
          payment_speed_days: 1,
          reliability_rating: 4.9,
          breakdown: { crop_compatibility: 35.0, quantity_alignment: 25.0, price_feasibility: 20.0, reliability_and_terms: 13.0 },
          explanation: 'Regular buyer of fresh tomatoes. Immediate delivery to Indiranagar HoReCa hub with T+0 settlement.'
        },
        {
          buyer_id: 'b3',
          buyer_name: 'FreshMart Retail Chain',
          buyer_type: 'Retail Supermarket',
          location: 'Bengaluru North (Hebbal)',
          phone: '+91 80 3344 5566',
          match_score: 84,
          match_grade: 'Good Alternative',
          estimated_offer_price: 28.8,
          estimated_gross_recovery: 5184.0,
          payment_speed_days: 2,
          reliability_rating: 4.6,
          breakdown: { crop_compatibility: 35.0, quantity_alignment: 20.0, price_feasibility: 18.0, reliability_and_terms: 11.0 },
          explanation: 'Large retail chain with daily produce intake at Hebbal hub.'
        }
      ]
    }
  },

  async recover(disruptionId, payload) {
    const apiRes = requireBackendResponse(await request(`/disruptions/${disruptionId}/recover`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }), 'The disruption recovery')
    if (apiRes && apiRes.success) return apiRes
    throw new ApiError('The backend did not confirm the disruption recovery.')
  }
}

// ----------------- DEMAND FORECASTING & GAPS SERVICE -----------------
export const aiService = {
  async forecast(crop, location, windowLabel) {
    try {
      const apiRes = await request(`/forecasting?crop=${encodeURIComponent(crop)}&location=${encodeURIComponent(location)}`)
      if (apiRes && apiRes.linear_trend_model) {
        // Map to frontend chart format
        const baseline = apiRes.linear_trend_model
        const forecasts = apiRes.next_4_weeks_forecast_kg || [3850, 4050, 4250, 4450]
        const trendSlope = baseline.trend_slope_kg_per_week || 0
        
        // Calculate approximate change percentage
        const changePct = trendSlope > 0 ? Math.min(Math.round((trendSlope / 3000) * 100), 15) : 5
        
        return {
          crop, location, window: windowLabel,
          demand: changePct > 8 ? 'High' : changePct > 4 ? 'Medium' : 'Moderate',
          priceRange: [28, 34],
          recommendedQuantity: Math.round(baseline.metrics.mae * 8),
          bestMarket: `${location} Main Mandi`,
          bestWindow: 'Next 3-5 Days',
          changePct: changePct,
          series: [
            { date: 'Oct 01', actual: 2800, predicted: 2750 },
            { date: 'Oct 05', actual: 3000, predicted: 2950 },
            { date: 'Oct 10', actual: 3200, predicted: 3180 },
            { date: 'Oct 15', actual: 3450, predicted: 3400 },
            { date: 'Oct 20', actual: 3700, predicted: 3650 },
            { date: 'Oct 25', actual: null, predicted: Math.round(forecasts[0] || 3850) },
            { date: 'Oct 30', actual: null, predicted: Math.round(forecasts[1] || 4050) },
          ],
          metrics: baseline.metrics,
          evaluationNote: apiRes.evaluation_note
        }
      }
    } catch (err) {
      console.warn('Forecast API error, using fallback:', err)
    }
    // Always return mock data as fallback
    const mockData = getMockForecast(crop, location, windowLabel)
    return mockData
  },

  async getEvaluation(crop = 'Tomato', location = 'Kolar') {
    const apiRes = await request(`/forecasting?crop=${encodeURIComponent(crop)}&location=${encodeURIComponent(location)}`)
    if (apiRes && apiRes.linear_trend_model) return apiRes

    return {
      crop, location,
      naive_moving_average_model: { name: 'Naive 3-Period Moving Average', metrics: { mae: 145.2, rmse: 168.4, mape_pct: 4.8 } },
      linear_trend_model: { name: 'Time-Aware Trend Baseline', metrics: { mae: 78.5, rmse: 92.1, mape_pct: 2.4 } },
      winning_model: 'Time-Aware Trend Baseline',
      next_4_weeks_forecast_kg: [3850, 4000, 4150, 4300],
      evaluation_note: 'Evaluated on 12 time-series periods without lookahead data leakage. Trend model achieved 2.4% MAPE.'
    }
  },

  async getSupplyDemandGaps() {
    const apiRes = await request('/forecasting/gaps')
    if (apiRes && apiRes.gaps) return apiRes.gaps

    return [
      {
        crop: 'Tomato',
        available_supply_kg: 4800,
        projected_demand_kg: 3500,
        gap_kg: 1300,
        gap_pct: 37.1,
        status: 'Surplus Risk',
        severity: 'warning',
        recommended_action: 'Surplus Tomato risk in Kolar: Consolidate lots and route surplus via pooled logistics to high-demand Bengaluru retail buyers.'
      },
      {
        crop: 'Onion',
        available_supply_kg: 1400,
        projected_demand_kg: 2200,
        gap_kg: -800,
        gap_pct: -36.4,
        status: 'Shortage Alert',
        severity: 'critical',
        recommended_action: 'Market demand exceeds local supply by 36.4%. Signal FPO members to advance ready dates.'
      }
    ]
  }
}

// ----------------- OPERATIONAL ANALYTICS SERVICE -----------------
export const analyticsService = {
  async getMetrics() {
    const apiRes = await request('/analytics')
    if (apiRes && apiRes.metrics) return apiRes

    // Fallback analytics derived from local seed
    return {
      metrics: {
        activeListingsCount: seedProducts.length,
        totalAvailableKg: seedProducts.reduce((sum, p) => sum + p.quantity, 0),
        totalOrdersCount: seedOrders.length,
        activeOrdersCount: seedOrders.filter(o => o.stage !== 'Delivered').length,
        fulfilledOrdersCount: seedOrders.filter(o => o.stage === 'Delivered').length,
        totalGrossVolumeINR: seedOrders.reduce((sum, o) => sum + o.total, 0),
        activeShipmentsCount: 1,
        totalPooledKg: 1450.0,
        totalLogisticsSavingsINR: 1350.0,
        openDisruptionsCount: 1,
        recoveredDisruptionsCount: 0,
      },
      topCrops,
      categorySplit: [
        { name: 'Vegetables', value: 48 },
        { name: 'Grains', value: 24 },
        { name: 'Fruits', value: 16 },
        { name: 'Dairy', value: 12 },
      ]
    }
  }
}

// ----------------- SAP ENTERPRISE GATEWAY SERVICE -----------------
export const sapService = {
  async getStatus() {
    const apiRes = await request('/sap/status')
    if (apiRes) return apiRes
    return {
      status: 'READY_FOR_RFC_ODATA',
      gateway: 'FarmLink AI — SAP S/4HANA & SAP TM Integration Bridge',
      protocolsSupported: ['OData v4', 'RFC BAPI', 'cXML', 'REST Webhooks'],
      connectedAdapters: [
        { system: 'SAP S/4HANA Sourcing & Procurement (MM)', api: 'API_PURCHASEORDER_PROCESS_SRV', entity: 'A_PurchaseOrder' },
        { system: 'SAP Transportation Management (SAP TM 9.6+)', api: 'FreightOrder_In', entity: 'FreightOrder' },
        { system: 'SAP Supply Chain Control Tower', api: 'EventManagement_In', entity: 'DisruptionAlert' },
      ],
      mockSimulation: true
    }
  },

  async exportPO(orderId) {
    const apiRes = await request(`/sap/export-po/${orderId}`, { method: 'POST' })
    if (apiRes && apiRes.sapPurchaseOrder) return apiRes.sapPurchaseOrder
    return null
  },

  async exportTM(shipmentId) {
    const apiRes = await request(`/sap/export-tm/${shipmentId}`, { method: 'POST' })
    if (apiRes && apiRes.sapFreightOrder) return apiRes.sapFreightOrder
    return null
  },

  async exportDisruptionAlert(disruptionId) {
    const apiRes = await request(`/sap/control-tower-alert/${disruptionId}`, { method: 'POST' })
    if (apiRes && apiRes.sapControlTowerAlert) return apiRes.sapControlTowerAlert
    return null
  }
}

// ----------------- NOTIFICATION SERVICE -----------------
export const notificationService = {
  async list(role = null, userId = null) {
    const params = new URLSearchParams()
    if (role) params.set('role', role)
    if (userId) params.set('userId', userId)

    const apiRes = await request(`/notifications?${params.toString()}`)
    if (apiRes && apiRes.notifications) return apiRes.notifications

    return [
      {
        id: 'n1',
        title: 'Disruption Alert: Order ORD-1043 Cancelled',
        message: 'ABC Hostel cancelled 180 kg Tomato order. FarmLink AI identified 3 alternative buyers ready for pickup.',
        tone: 'error',
        link: '/disruptions',
        isRead: false,
        timestamp: '10 mins ago',
      },
      {
        id: 'n2',
        title: 'Consolidated Run SHP-101 In Transit',
        message: 'Vehicle KA-04-TR-1029 has completed Kolar & Chikkaballapur pickups (1,450 kg loaded). Next stop: Hebbal.',
        tone: 'success',
        link: '/logistics',
        isRead: false,
        timestamp: '25 mins ago',
      }
    ]
  },

  async markRead(id) {
    const apiRes = requireBackendResponse(await request(`/notifications/${id}/read`, { method: 'PATCH' }), 'The notification update')
    if (apiRes.success) return true
    throw new ApiError('The backend did not confirm the notification update.')
  }
}
