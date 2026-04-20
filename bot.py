import os
from dataclasses import dataclass

import discord


MAJOR_PAIRS = {
    "EURUSD": {"contract_size": 100000, "pip_size": 0.0001, "description": "Euro / US Dollar"},
    "GBPUSD": {"contract_size": 100000, "pip_size": 0.0001, "description": "British Pound / US Dollar"},
    "USDJPY": {"contract_size": 100000, "pip_size": 0.01, "description": "US Dollar / Japanese Yen"},
    "USDCHF": {"contract_size": 100000, "pip_size": 0.0001, "description": "US Dollar / Swiss Franc"},
    "AUDUSD": {"contract_size": 100000, "pip_size": 0.0001, "description": "Australian Dollar / US Dollar"},
    "NZDUSD": {"contract_size": 100000, "pip_size": 0.0001, "description": "New Zealand Dollar / US Dollar"},
    "USDCAD": {"contract_size": 100000, "pip_size": 0.0001, "description": "US Dollar / Canadian Dollar"},
}

MINOR_PAIRS = {
    "EURJPY": {"contract_size": 100000, "pip_size": 0.01, "description": "Euro / Japanese Yen"},
    "EURGBP": {"contract_size": 100000, "pip_size": 0.0001, "description": "Euro / British Pound"},
    "GBPJPY": {"contract_size": 100000, "pip_size": 0.01, "description": "British Pound / Japanese Yen"},
    "CHFJPY": {"contract_size": 100000, "pip_size": 0.01, "description": "Swiss Franc / Japanese Yen"},
}

INSTRUMENTS = {
    "XAUUSD": {"contract_size": 100, "pip_size": 0.1, "description": "Gold (XAU/USD)"},
    "US30": {"contract_size": 1, "pip_size": 1.0, "description": "Dow Jones (index)"},
    "US100": {"contract_size": 1, "pip_size": 1.0, "description": "Nasdaq (index)"},
    "US500": {"contract_size": 1, "pip_size": 1.0, "description": "S&P 500 (index)"},
    "DE40": {"contract_size": 1, "pip_size": 1.0, "description": "DAX 40 (index)"},
    "BTCUSD": {"contract_size": 1, "pip_size": 1.0, "description": "Bitcoin/USD (crypto)"},
}

CATEGORY_MAP = {
    "major": MAJOR_PAIRS,
    "minor": MINOR_PAIRS,
    "other": INSTRUMENTS,
}

RISK_MAP = {
    "0.25": 0.0025,
    "0.50": 0.005,
    "1.00": 0.01,
    "2.00": 0.02,
}

LEVERAGE_MAP = {
    "1:10": 10.0,
    "1:20": 20.0,
    "1:30": 30.0,
    "1:50": 50.0,
    "1:100": 100.0,
}

RR_MAP = {
    "1:1": 1.0,
    "1:1.5": 1.5,
    "1:2": 2.0,
    "1:3": 3.0,
}


def fmt_num(v: float, d: int = 2) -> str:
    return f"{v:,.{d}f}"


def pip_value_per_lot(
    symbol: str,
    contract_size: float,
    pip_size: float,
    price: float,
    account_currency: str = "USD",
    quote_to_account_rate: float | None = None,
) -> tuple[float, bool, str]:
    """
    Returns:
      pip_value_per_lot_in_account_currency,
      is_approximation,
      note

    Precise core:
      pip_value_in_quote = contract_size * pip_size

    Conversion:
      - direct (quote == account): pip_value_quote
      - inverse (base == account): pip_value_quote / price
      - cross: pip_value_quote * quote_to_account_rate
    """
    if len(symbol) == 6 and symbol.isalpha():
        base = symbol[:3]
        quote = symbol[3:]
        pip_value_quote = contract_size * pip_size

        if quote == account_currency:
            return pip_value_quote, False, "direct quote"

        if base == account_currency:
            return pip_value_quote / price, False, "inverse quote"

        if quote_to_account_rate is not None and quote_to_account_rate > 0:
            return pip_value_quote * quote_to_account_rate, False, "cross via provided quote->account rate"

        approx = pip_value_quote / price
        return approx, True, "cross pair approximation (missing quote->account rate)"

    pip_value = contract_size * pip_size
    return pip_value, False, "non-forex contract model"


@dataclass
class SessionData:
    owner_id: int
    account_size: float
    entry_price: float
    sl_pips: float
    risk_pct: float | None = None
    leverage: float | None = None
    category: str | None = None
    instrument: str | None = None
    size_mode: str | None = None
    rr: float | None = None
    direction: str = "long"


def calculate(data: SessionData) -> dict[str, float | str]:
    if not all([
        data.risk_pct,
        data.leverage,
        data.category,
        data.instrument,
        data.size_mode,
        data.rr,
    ]):
        raise ValueError("Session not complete")

    meta = CATEGORY_MAP[data.category][data.instrument]
    contract_size = float(meta["contract_size"])
    pip_size = float(meta["pip_size"])
    rr = float(data.rr)

    pip_value_lot, pip_value_is_approx, pip_note = pip_value_per_lot(
        data.instrument,
        contract_size,
        pip_size,
        data.entry_price,
        account_currency="USD",
        quote_to_account_rate=None,
    )
    mode_multiplier = 1.0 if data.size_mode == "lots" else 0.01
    pip_value_mode = pip_value_lot * mode_multiplier

    risk_amount = data.account_size * float(data.risk_pct)
    loss_per_mode = data.sl_pips * pip_value_mode
    position_mode_units = risk_amount / loss_per_mode if loss_per_mode > 0 else 0.0

    total_lots = position_mode_units * mode_multiplier
    notional_units = total_lots * contract_size

    sl_distance_price = data.sl_pips * pip_size
    if data.direction == "long":
        sl_price = data.entry_price - sl_distance_price
        tp_price = data.entry_price + (sl_distance_price * rr)
    else:
        sl_price = data.entry_price + sl_distance_price
        tp_price = data.entry_price - (sl_distance_price * rr)

    profit_pips = data.sl_pips * rr
    max_profit = total_lots * (profit_pips * pip_value_lot)

    notional_value = notional_units * data.entry_price
    margin_required = notional_value / float(data.leverage)
    min_win_rate = 1 / (1 + rr) if rr > 0 else 0.0

    return {
        "symbol": data.instrument,
        "description": str(meta["description"]),
        "contract_size": contract_size,
        "pip_size": pip_size,
        "pip_value_lot": pip_value_lot,
        "pip_value_mode": pip_value_mode,
        "risk_amount": risk_amount,
        "position_mode_units": position_mode_units,
        "total_lots": total_lots,
        "notional_units": notional_units,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "max_loss": risk_amount,
        "max_profit": max_profit,
        "margin_required": margin_required,
        "min_win_rate": min_win_rate,
        "pip_value_is_approx": "yes" if pip_value_is_approx else "no",
        "pip_note": pip_note,
        "sl_price_move": sl_distance_price,
        "sl_pips_check": sl_distance_price / pip_size if pip_size > 0 else 0.0,
    }


class GenericSelect(discord.ui.Select):
    def __init__(self, placeholder: str, options: list[discord.SelectOption], handler: str) -> None:
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, row=0)
        self.handler = handler

    async def callback(self, interaction: discord.Interaction) -> None:
        view: WizardView = self.view
        await view.handle_select(interaction, self.handler, self.values[0])


class InputModal(discord.ui.Modal, title="Zadaj udaje o ucte a vstupe"):
    account_size = discord.ui.TextInput(label="Stav uctu (napr. 100000)", placeholder="Zadaj sumu v USD", required=True)
    entry_price = discord.ui.TextInput(label="Entry cena (napr. 2720.3 pre XAUUSD)", placeholder="Vloz cenu vstupu", required=True)
    sl_pips = discord.ui.TextInput(label="Stop-loss offset (v pipsoch, napr. 50)", placeholder="Kolko pips od entry je SL?", required=True)

    def __init__(self, owner_id: int) -> None:
        super().__init__()
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Tento formular je iba pre autora prikazu.", ephemeral=True)
            return

        try:
            account = float(str(self.account_size).replace(",", ".").strip())
            entry = float(str(self.entry_price).replace(",", ".").strip())
            sl = float(str(self.sl_pips).replace(",", ".").strip())
            if account <= 0 or entry <= 0 or sl <= 0:
                raise ValueError("Values must be positive")
        except Exception:
            await interaction.response.send_message(
                "Neplatny vstup. Priklad: account 50000, entry 4831.61, SL 250",
                ephemeral=True,
            )
            return

        data = SessionData(owner_id=self.owner_id, account_size=account, entry_price=entry, sl_pips=sl)
        view = WizardView(data)
        await interaction.response.send_message(embed=view.build_step_embed("risk"), view=view, ephemeral=True)


class StartPromptView(discord.ui.View):
    def __init__(self, owner_id: int) -> None:
        super().__init__(timeout=10 * 60)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Toto tlacidlo je iba pre autora prikazu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Open Calculator", style=discord.ButtonStyle.primary)
    async def open_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(InputModal(owner_id=self.owner_id))


class WizardView(discord.ui.View):
    def __init__(self, data: SessionData) -> None:
        super().__init__(timeout=15 * 60)
        self.data = data
        self.step = "risk"
        self.render_step()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.data.owner_id:
            await interaction.response.send_message("Tento wizard je iba pre autora prikazu.", ephemeral=True)
            return False
        return True

    def render_step(self) -> None:
        self.clear_items()

        if self.step == "risk":
            options = [
                discord.SelectOption(label="0.25%", value="0.25"),
                discord.SelectOption(label="0.5%", value="0.50"),
                discord.SelectOption(label="1%", value="1.00"),
                discord.SelectOption(label="2%", value="2.00"),
            ]
            self.add_item(GenericSelect("Vyber si teraz risk", options, "risk"))
            return

        if self.step == "leverage":
            options = [discord.SelectOption(label=k, value=k) for k in LEVERAGE_MAP.keys()]
            self.add_item(GenericSelect("Vyber si paku", options, "leverage"))
            return

        if self.step == "category":
            options = [
                discord.SelectOption(label="Major", value="major"),
                discord.SelectOption(label="Minor", value="minor"),
                discord.SelectOption(label="Ostatne", value="other"),
            ]
            self.add_item(GenericSelect("Vyber si kategoriu instrumentu", options, "category"))
            return

        if self.step == "instrument":
            assert self.data.category is not None
            options = [
                discord.SelectOption(label=sym, value=sym, description=meta["description"][:100])
                for sym, meta in CATEGORY_MAP[self.data.category].items()
            ]
            self.add_item(GenericSelect("Vyber si instrument", options, "instrument"))
            return

        if self.step == "size_mode":
            self.add_item(self.lots_btn)
            self.add_item(self.micro_btn)
            return

        if self.step == "rr":
            options = [discord.SelectOption(label=k, value=k) for k in RR_MAP.keys()]
            self.add_item(GenericSelect("Vyber si Risk-to-Reward pomer", options, "rr"))
            return

    def status_lines(self) -> str:
        lines = [
            f"Stav uctu: `{fmt_num(self.data.account_size, 2)}`",
            f"Entry: `{fmt_num(self.data.entry_price, 5)}`",
            f"Stop-loss offset: `{fmt_num(self.data.sl_pips, 2)} pips`",
        ]
        if self.data.risk_pct is not None:
            lines.append(f"Risk: `{fmt_num(self.data.risk_pct * 100, 2)}%`")
        if self.data.leverage is not None:
            lines.append(f"Paka: `1:{int(self.data.leverage)}`")
        if self.data.category is not None:
            lines.append(f"Kategoria: `{self.data.category}`")
        if self.data.instrument is not None:
            lines.append(f"Instrument: `{self.data.instrument}`")
        if self.data.size_mode is not None:
            lines.append(f"Rezim: `{self.data.size_mode}`")
        if self.data.rr is not None:
            lines.append(f"R:R: `1:{fmt_num(self.data.rr, 2)}`")
        return "\n".join(lines)

    def build_step_embed(self, step_name: str) -> discord.Embed:
        prompt_map = {
            "risk": "Vyber si teraz risk",
            "leverage": "Vyber si paku",
            "category": "Vyber si kategoriu instrumentu",
            "instrument": "Vyber si instrument z kategorie",
            "size_mode": "Vyber rezim pozicie",
            "rr": "Vyber si Risk-to-Reward pomer",
        }
        embed = discord.Embed(title="Risk Management Wizard", color=discord.Color.blurple())
        embed.description = f"{self.status_lines()}\n\n{prompt_map[step_name]}"
        return embed

    def build_final_embed(self) -> discord.Embed:
        out = calculate(self.data)
        embed = discord.Embed(title=f"Vysledok - {out['symbol']}", color=discord.Color.green())
        embed.add_field(
            name="Input",
            value=(
                f"Account: `{fmt_num(self.data.account_size, 2)}`\n"
                f"Entry: `{fmt_num(self.data.entry_price, 5)}`\n"
                f"SL pips: `{fmt_num(self.data.sl_pips, 2)}`\n"
                f"Risk: `{fmt_num(float(self.data.risk_pct) * 100, 2)}%`\n"
                f"Leverage: `1:{int(float(self.data.leverage))}`"
            ),
            inline=True,
        )
        mode_label = "lots" if self.data.size_mode == "lots" else "micro lots"
        embed.add_field(
            name="Position",
            value=(
                f"Instrument: `{out['symbol']}`\n"
                f"Size mode: `{mode_label}`\n"
                f"Position size: `{fmt_num(float(out['position_mode_units']), 3)} {mode_label}`\n"
                f"Total lots: `{fmt_num(float(out['total_lots']), 4)}`\n"
                f"Units: `{fmt_num(float(out['notional_units']), 0)}`"
            ),
            inline=True,
        )
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(
            name="Levels",
            value=(
                f"SL price: `{fmt_num(float(out['sl_price']), 5)}`\n"
                f"TP price: `{fmt_num(float(out['tp_price']), 5)}`\n"
                f"R:R: `1:{fmt_num(float(self.data.rr), 2)}`\n"
                f"SL move: `{fmt_num(float(out['sl_price_move']), 5)}` price units"
            ),
            inline=True,
        )
        embed.add_field(
            name="Risk Metrics",
            value=(
                f"Pip value/lot: `{fmt_num(float(out['pip_value_lot']), 4)}`\n"
                f"Max loss: `-{fmt_num(float(out['max_loss']), 2)}`\n"
                f"Max profit: `+{fmt_num(float(out['max_profit']), 2)}`\n"
                f"Required margin: `{fmt_num(float(out['margin_required']), 2)}`\n"
                f"Min win-rate: `{fmt_num(float(out['min_win_rate']) * 100, 2)}%`\n"
                f"Pip model: `{out['pip_note']}`"
            ),
            inline=True,
        )
        if str(out["pip_value_is_approx"]) == "yes":
            embed.set_footer(text="Pozor: cross pair pip value je aproximacia. Pre presnost treba quote->account konverzny kurz.")
        else:
            embed.set_footer(text="Pip value pouziva presny direct/inverse model; pre cross pary treba konverzny kurz.")
        return embed

    async def handle_select(self, interaction: discord.Interaction, handler: str, value: str) -> None:
        if handler == "risk":
            self.data.risk_pct = RISK_MAP[value]
            self.step = "leverage"
            self.render_step()
            await interaction.response.edit_message(embed=self.build_step_embed("leverage"), view=self)
            return

        if handler == "leverage":
            self.data.leverage = LEVERAGE_MAP[value]
            self.step = "category"
            self.render_step()
            await interaction.response.edit_message(embed=self.build_step_embed("category"), view=self)
            return

        if handler == "category":
            self.data.category = value
            self.step = "instrument"
            self.render_step()
            await interaction.response.edit_message(embed=self.build_step_embed("instrument"), view=self)
            return

        if handler == "instrument":
            self.data.instrument = value
            self.step = "size_mode"
            self.render_step()
            await interaction.response.edit_message(embed=self.build_step_embed("size_mode"), view=self)
            return

        if handler == "rr":
            self.data.rr = RR_MAP[value]
            self.clear_items()
            await interaction.response.edit_message(embed=self.build_final_embed(), view=self)
            return

    @discord.ui.button(label="Loty", style=discord.ButtonStyle.primary, row=1)
    async def lots_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.step != "size_mode":
            await interaction.response.send_message("Najprv prejdi predchadzajuce kroky.", ephemeral=True)
            return
        self.data.size_mode = "lots"
        self.step = "rr"
        self.render_step()
        await interaction.response.edit_message(embed=self.build_step_embed("rr"), view=self)

    @discord.ui.button(label="MicroKontrakty", style=discord.ButtonStyle.secondary, row=1)
    async def micro_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.step != "size_mode":
            await interaction.response.send_message("Najprv prejdi predchadzajuce kroky.", ephemeral=True)
            return
        self.data.size_mode = "micro"
        self.step = "rr"
        self.render_step()
        await interaction.response.edit_message(embed=self.build_step_embed("rr"), view=self)


class TraderBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if message.content.strip().lower() != "start":
            return

        view = StartPromptView(owner_id=message.author.id)
        await message.channel.send(
            f"{message.author.mention}, klikni na tlacidlo nizsie a spusti kalkulator risk managementu.",
            view=view,
        )

    async def on_ready(self) -> None:
        print(f"Logged in as {self.user} (ID: {self.user.id})")


def main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN environment variable.")
    bot = TraderBot()
    bot.run(token)


if __name__ == "__main__":
    main()
