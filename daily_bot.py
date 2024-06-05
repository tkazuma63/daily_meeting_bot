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
from config import OPENAI_API_TOKEN, DISCORD_SERVER_GUILD

TOKEN: str = OPENAI_API_TOKEN
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
    file = File(stream, file_name="messages.txt")
    await event.send(components=[], files=file, ephemeral=True)
    stream.close()


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


if __name__ == "__main__":
    bot.start()
