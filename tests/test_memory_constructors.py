def test_outcome_linker_no_args():
    from monika.application.analysis.memory.outcome_linker import OutcomeLinker

    linker = OutcomeLinker()
    assert linker is not None
    assert isinstance(linker, OutcomeLinker)


def test_trade_reflector_no_args():
    from monika.application.analysis.memory.reflector import TradeReflector

    reflector = TradeReflector()
    assert reflector is not None
    assert isinstance(reflector, TradeReflector)
