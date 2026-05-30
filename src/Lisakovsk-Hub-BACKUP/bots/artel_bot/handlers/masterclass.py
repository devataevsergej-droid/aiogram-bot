import logging
from aiogram import F, Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from src.artel_bot.states.masterclass import WorkshopRegistration
from src.artel_bot.keyboards.masterclass import workshop_keyboard

# Временный импорт для db (потом перенесём в core)
from src.job_bot.db import SupabaseRepository

router = Router(name="artel_masterclass")
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    """Обработчик /start"""
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать на регистрацию мастер-классов!\n\n"
        "Выберите интересующее направление:",
        reply_markup=workshop_keyboard()
    )


@router.callback_query(F.data.startswith("workshop:"))
async def workshop_chosen(callback: CallbackQuery, state: FSMContext):
    """Выбор мастер-класса"""
    workshop = callback.data.split(":")[1]
    workshop_names = {
        "candles": "🕯 Свечи",
        "soap": "🧼 Мыло",
        "gypsum": "🪨 Гипс",
        "epoxy": "✨ Эпоксидная смола",
        "undecided": "🤔 Пока не решил"
    }
    
    await state.update_data(workshop=workshop_names.get(workshop, workshop))
    await state.set_state(WorkshopRegistration.name)
    
    await callback.message.edit_text(
        f"Вы выбрали: {workshop_names.get(workshop, workshop)}\n\n"
        f"Введите ваше имя:"
    )
    await callback.answer()


@router.message(WorkshopRegistration.name)
async def name_entered(message: Message, state: FSMContext):
    """Ввод имени"""
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("❌ Пожалуйста, введите настоящее имя (минимум 2 символа):")
        return
    
    await state.update_data(full_name=message.text.strip())
    await state.set_state(WorkshopRegistration.phone)
    await message.answer("📞 Введите номер телефона для связи:")


@router.message(WorkshopRegistration.phone)
async def phone_entered(message: Message, state: FSMContext, repo: SupabaseRepository):
    """Ввод телефона и сохранение в БД"""
    phone = message.text.strip()
    if len(phone) < 5:
        await message.answer("❌ Пожалуйста, введите корректный номер телефона:")
        return
    
    data = await state.get_data()
    
    # Сохраняем в Supabase
    try:
        await repo.client.table("masterclass_registrations").insert({
            "user_id": message.from_user.id,
            "username": message.from_user.username,
            "full_name": data.get("full_name"),
            "phone": phone,
            "workshop": data.get("workshop"),
        }).execute()
        
        await message.answer(
            "✅ Вы успешно записаны!\n\n"
            "С вами свяжутся при необходимости.\n"
            "До встречи на мастер-классе!"
        )
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения регистрации: {e}")
        await message.answer(
            "❌ Произошла ошибка при сохранении. Пожалуйста, попробуйте позже."
        )
        