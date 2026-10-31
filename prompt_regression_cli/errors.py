class PromptRegressionError(Exception):
    pass


class ConfigError(PromptRegressionError):
    pass


class CaseError(PromptRegressionError):
    pass


class TemplateError(PromptRegressionError):
    pass


class RequestError(PromptRegressionError):
    pass


class ReportError(PromptRegressionError):
    pass
