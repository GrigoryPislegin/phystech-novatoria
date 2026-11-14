"""Public error codes contain no provider messages, paths or source text."""


class BudgetLimit(ValueError):
    pass


class ModelOutputError(ValueError):
    pass


class PrivacyError(RuntimeError):
    """Only static categories/counts; never text, paths or model-supplied keys."""
    def __init__(self, code, findings=None):
        self.code = code
        allowed = {'EMAIL','LINK','HANDLE','PHONE','DATE','SECRET','IDENTITY','CONTACT',
                   'PERSON','ORG','LOCATION','KNOWN_VALUE'}
        self.diagnostic = {'stage':'privacy', 'direction':'outbound',
                           'findings':{k:v for k,v in (findings or {}).items()
                                       if k in allowed and type(v) is int and v > 0}}
        super().__init__(code)


class RunStopped(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def error_code(exc, stage=''):
    if isinstance(exc, PrivacyError):
        return exc.code
    if isinstance(exc, RunStopped):
        return exc.code
    if isinstance(exc, BudgetLimit):
        return 'budget_limit'
    if isinstance(exc, ModelOutputError) or (stage.endswith('_validation') and isinstance(exc, ValueError)):
        return 'model_invalid'
    # Only exact, known local messages may affect the public diagnostic.
    known = {'privacy_untrusted_reference', 'privacy_residual_findings', 'privacy_models_missing_or_invalid', 'privacy_detector_failed', 'privacy_closed',
             'openai_key_missing', 'invalid_job_set', 'input_symlink', 'input_invalid',
             'input_too_large', 'input_unsupported', 'output_unavailable', 'invalid_deadline', 'invalid_metadata',
             'budget_must_be_between_0_and_5', 'model_refusal_or_incomplete'}
    if type(exc) in (ValueError, RuntimeError) and str(exc) in known:
        return str(exc)
    if stage in {'facts', 'requirements', 'evaluation', 'facts_validation', 'requirements_validation', 'evaluation_validation'}:
        return stage.split('_')[0] + '_failed'
    return 'operation_failed'
