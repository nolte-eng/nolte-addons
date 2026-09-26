def post_init_hook(env):
    """Provide a useful short list on a fresh installation."""
    rates = env["nolte.bmf.rate"].sudo()
    if not rates.search_count([("show_in_report", "=", True)]):
        rates.search([("rate_key", "in", ["DE", "CH", "AT", "IT", "FR", "NL", "CN"])]).write({
            "show_in_report": True,
        })
