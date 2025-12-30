from aiogram.fsm.state import StatesGroup, State


class ProposalStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_body = State()

class CreateFractal(StatesGroup):
    name = State()
    description = State()
    round_time = State()
    start_date = State()    
    timezone = State()