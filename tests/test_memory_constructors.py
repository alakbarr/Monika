def test_outcome_linker_no_args():
    from analysis.memory.outcome_linker import OutcomeLinker
    OutcomeLinker()  # harus tidak raise

def test_trade_reflector_no_args():
    from analysis.memory.reflector import TradeReflector
    TradeReflector()  # harus tidak raise
