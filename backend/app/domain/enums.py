from enum import Enum


class AppointmentStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled_by_patient = "cancelled_by_patient"
    cancelled_by_clinic = "cancelled_by_clinic"
    rescheduled = "rescheduled"
    unconfirmed = "unconfirmed"
    attended = "attended"
    no_show = "no_show"


class ConversationStatus(str, Enum):
    active = "active"
    escalated = "escalated"
    resolved = "resolved"
    archived = "archived"


class ConversationChannel(str, Enum):
    whatsapp = "whatsapp"
    web = "web"


class MessageOrigin(str, Enum):
    patient = "patient"
    bot = "bot"
    human = "human"


class UserRole(str, Enum):
    admin = "admin"
    recepcionista = "recepcionista"


class TenantStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    cancelled = "cancelled"


class TenantPlan(str, Enum):
    basic = "basic"
    professional = "professional"
    premium = "premium"
