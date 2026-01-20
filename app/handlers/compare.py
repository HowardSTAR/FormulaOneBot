from aiogram import Router
from aiogram.filters import CommandObject, Command
from aiogram.types import Message, BufferedInputFile
# Import the async data function and the render function
from app.f1_data import get_drivers_comparison_async
from app.utils.image_render import create_comparison_image

router = Router()


# TODO сделать нормальное сравнение
@router.message(Command("compare"))
async def cmd_compare_drivers(message: Message, command: CommandObject):
    """
    Usage: /compare VER HAM
    """
    if not command.args:
        await message.answer("Использование: /compare <CODE1> <CODE2>\nПример: /compare VER NOR")
        return

    args = command.args.split()
    if len(args) < 2:
        await message.answer("Укажите двух пилотов. Пример: /compare VER NOR")
        return

    d1_code = args[0].strip()
    d2_code = args[1].strip()
    season = 2024  # Or datetime.now().year

    # 1. Get Data
    msg = await message.answer("📊 Собираю данные и строю график...")

    stats = await get_drivers_comparison_async(season, d1_code, d2_code)

    if not stats:
        await msg.edit_text("❌ Не удалось найти данные. Проверьте коды пилотов.")
        return

    # 2. Render Image (Run in thread to avoid blocking)
    import asyncio
    img_buf = await asyncio.to_thread(
        create_comparison_image,
        stats["driver1"],
        stats["driver2"],
        stats["labels"]
    )

    # 3. Send
    photo = BufferedInputFile(img_buf.read(), filename="compare.png")
    await message.answer_photo(
        photo,
        caption=f"⚔️ Сравнение: {stats['driver1']['code']} vs {stats['driver2']['code']}"
    )
    await msg.delete()