from discord import utils
from datetime import datetime, timedelta, timezone
from io import StringIO
from interactions import (
    Client,
    listen,
    Modal,
    ShortText,
    SlashContext,
    slash_command,
    modal_callback,
    ModalContext,
    Button,
    ButtonStyle,
    ComponentContext,
    component_callback,
    File,
)
from config import DISCORD_BOT_TOKEN, DISCORD_SERVER_GUILD

import re
import logging

# ログの設定
logging.basicConfig(
    filename="process.log",
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(message)s",
)

TOKEN: str = DISCORD_BOT_TOKEN
GUILD: int = DISCORD_SERVER_GUILD

bot = Client(token=TOKEN, debug_scope=GUILD)


@listen()
async def on_ready():
    print("Bot is ready!")
    print(f"This bot is owned by {bot.owner}")


@slash_command(name="modal", description="Get date and display modal")
async def my_command_function(ctx: SlashContext):
    current_date = datetime.now()
    first_day_of_last_month = (current_date.replace(day=1) - timedelta(days=1)).replace(
        day=1
    )
    last_day_of_last_month = current_date.replace(day=1) - timedelta(days=1)

    start_date = first_day_of_last_month.strftime("%Y-%m-%d")
    end_date = last_day_of_last_month.strftime("%Y-%m-%d")

    my_modal = Modal(
        ShortText(
            label="Start Date",
            custom_id="start_date_text",
            value=start_date,
            min_length=10,
        ),
        ShortText(
            label="End Date",
            custom_id="end_date_text",
            value=end_date,
            min_length=10,
        ),
        title="Date Range Modal",
        custom_id="date_range_modal",
    )
    await ctx.send_modal(modal=my_modal)


@modal_callback("date_range_modal")
async def on_modal_answer(ctx: ModalContext, start_date_text: str, end_date_text: str):
    button = Button(
        custom_id="execute_button",
        style=ButtonStyle.GREEN,
        label="Execute",
    )
    await ctx.send(
        f"Start Date: {start_date_text}, End Date: {end_date_text}",
        components=button,
        ephemeral=True,
    )


@component_callback("execute_button")
async def on_component(event: ComponentContext):
    user_id = event.author.id
    content = event.message.content
    start_date_str, end_date_str = content.split("Start Date: ")[1].split(
        ", End Date: "
    )
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59
    )
    end_date = end_date.astimezone(timezone.utc)

    channel = event.channel
    messages = await get_messages_from_user_within_date_range(
        channel, user_id, start_date, end_date
    )

    stream = StringIO()
    for msg in messages:
        jst = msg.created_at + timedelta(hours=9)
        msg_str = (
            f"{msg.author.username}: {jst.strftime('%Y-%m-%d %H:%M:%S')}\n{msg.content}"
        )
        stream.write(msg_str + "\n\n")

    stream.seek(0)
    text = stream.getvalue()
    stream.close()

    # テキスト処理の実行
    output_with_date, output_without_date, errors = process_text(text)
    write_results(output_with_date, output_without_date, errors)

    # processed_output.txt の内容を読み込み表示
    with open("processed_output.txt", "r", encoding="utf-8") as file:
        processed_content = file.read()

    await event.send(
        content="テキスト処理が完了しました。以下が処理結果です：", ephemeral=True
    )
    await event.send(
        file=File(StringIO(processed_content), file_name="processed_output.txt"),
        ephemeral=True,
    )


async def get_messages_from_user_within_date_range(
    channel, user_id, start_date, end_date
):
    messages = []
    after_snowflake = utils.time_snowflake(start_date)
    before_snowflake = utils.time_snowflake(end_date)

    async for message in channel.history(
        after=after_snowflake, before=before_snowflake
    ):
        if (
            message.author.id == user_id
            and message.created_at.replace(tzinfo=timezone.utc) <= end_date
        ):
            messages.append(message)

    messages.sort(key=lambda msg: msg.created_at)
    print("Messages have been retrieved. Outputting to text file.")
    return messages


# 以下はdaily_to_sheet.pyの処理部分


def convert_to_hhmm(hours):
    try:
        h = int(hours)
        m = int((hours - h) * 60)
        return f"{h:02}:{m:02}"
    except Exception as e:
        logging.error(f"時間の変換中にエラーが発生しました: {e}")
        return "00:00"


def process_text(text):
    category_mapping = {
        "保守": 0,
        "機能開発": 1,
        "基盤改善": 2,
        "ISMAP": 3,
        "脆弱性": 4,
        "NHK": 5,
        "海外": 6,
        "アプリ": 7,
        "その他": 8,
    }

    date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})")
    task_pattern = re.compile(r"・【(.*?)】.*?\((\d+\.?\d*)h\)")

    lines = text.splitlines()
    result_with_date = []
    result_without_date = []
    errors = []
    date = ""
    categories = [0] * 9
    invalid_task = False

    for line in lines:
        date_match = date_pattern.search(line)
        if date_match:
            if date:
                total_hours = sum(categories)
                total_hours_hhmm = convert_to_hhmm(total_hours)
                categories_hhmm = [convert_to_hhmm(hours) for hours in categories]
                result_with_date.append(
                    f"{date},{','.join(categories_hhmm)},{total_hours_hhmm},{'☓' if invalid_task else '〇'}"
                )
                result_without_date.append(f"{','.join(categories_hhmm)}")
                invalid_task = False
            date = date_match.group(1)
            categories = [0] * 9

        task_match = task_pattern.findall(line)
        if task_match:
            for category, hours in task_match:
                if category in category_mapping:
                    categories[category_mapping[category]] += float(hours)
                else:
                    errors.append(f"{date} : {line}")
                    invalid_task = True
        elif "・【" in line:
            errors.append(f"{date} : {line}")
            invalid_task = True

    # 最後の日時の処理
    if date:
        total_hours = sum(categories)
        total_hours_hhmm = convert_to_hhmm(total_hours)
        categories_hhmm = [convert_to_hhmm(hours) for hours in categories]
        result_with_date.append(
            f"{date},{','.join(categories_hhmm)},{total_hours_hhmm},{'☓' if invalid_task else '〇'}"
        )
        result_without_date.append(f"{','.join(categories_hhmm)}")

    return result_with_date, result_without_date, errors


def write_results(output_with_date, output_without_date, errors):
    try:
        with open("processed_output.txt", "w", encoding="utf-8") as file:
            file.write("===== 項目「日付」、「合計」を含むデータ（確認用） =====\n")
            file.write(
                "備考が「〇」: OK ,  備考が「×」: タスクのテキストに誤りがある\n"
            )
            file.write(
                "日付,保守,機能開発,基盤改善,ISMAP,脆弱性,NHK,海外,アプリ,その他,合計,備考\n\n"
            )
            for line in output_with_date:
                file.write(line + "\n")

            file.write(
                "\n\n===== 項目「日付」、「合計」を含まないデータ（コピペ用） =====\n"
            )
            file.write("保守,機能開発,基盤改善,ISMAP,脆弱性,NHK,海外,アプリ,その他\n\n")
            for line in output_without_date:
                file.write(line + "\n")

            if errors:
                file.write(
                    "\n\n===== フォーマットに沿っていないタスク（修正用） =====\n"
                )
                for error in errors:
                    file.write(error + "\n")
    except Exception as e:
        logging.error(f"結果の書き込み中にエラーが発生しました: {e}")


if __name__ == "__main__":
    bot.start()
