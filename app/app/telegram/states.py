from aiogram.fsm.state import StatesGroup, State


class ProposalStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_body = State()