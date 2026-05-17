SPHERES = ("Строительство", "Торговля", "Услуги", "IT", "Другое")
SCHEDULES = ("Полный день", "Подработка", "Удалёнка", "Вахта")
NOT_IMPORTANT = "Не важно"

VACANCY_STATUS_PENDING = "pending"
VACANCY_STATUS_APPROVED = "approved"
VACANCY_STATUS_REJECTED = "rejected"
VACANCY_STATUS_CLOSED = "closed"

PAYMENT_TYPE_STARS = "stars"
PAYMENT_TYPE_MANUAL = "manual"
PAYMENT_STATUS_PENDING = "pending"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_REJECTED = "rejected"

FEATURE_UNLIMITED_VACANCIES = "unlimited_vacancies"
FEATURE_PIN_VACANCY = "pin_vacancy"
FEATURE_URGENT_BROADCAST = "urgent_broadcast"
FEATURE_VIP_SEEKER = "vip_seeker"

FEATURE_PRICES_STARS = {
    FEATURE_UNLIMITED_VACANCIES: 50,
    FEATURE_PIN_VACANCY: 30,
    FEATURE_URGENT_BROADCAST: 20,
    FEATURE_VIP_SEEKER: 30,
}

FEATURE_TITLES = {
    FEATURE_UNLIMITED_VACANCIES: "Безлимит вакансий на месяц",
    FEATURE_PIN_VACANCY: "Закреп вакансии на 3 дня",
    FEATURE_URGENT_BROADCAST: "Срочная рассылка всем соискателям",
    FEATURE_VIP_SEEKER: "VIP-статус соискателя на месяц",
}
