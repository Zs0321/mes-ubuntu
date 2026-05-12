from __future__ import annotations

from .config import BotConfig
from .handlers.router import MessageRouter
from .services.diagnosis_summary_service import DiagnosisSummaryService
from .services.feishu_client import FeishuBotClient
from .services.feishu_file_service import FeishuFileService
from .services.hermes_api_service import HermesApiService
from .services.issue_diagnosis_service import IssueDiagnosisService
from .services.llm_answer_service import LlmAnswerService
from .services.openai_compatible_service import OpenAiCompatibleService
from .services.probe_service import ProbeService
from .services.repository_catalog import RepositoryCatalog
from .services.resource_enrichment_service import ResourceEnrichmentService


def _create_reasoning_client(config: BotConfig):
    if config.hermes_base_url:
        return HermesApiService(
            base_url=config.hermes_base_url,
            workspace=config.hermes_workspace,
            timeout=config.llm_timeout,
            model=config.llm_model,
        )
    return OpenAiCompatibleService(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        timeout=config.llm_timeout,
    )


def create_router(config: BotConfig) -> MessageRouter:
    catalog = RepositoryCatalog()
    probe_service = ProbeService(config.workspace_root, catalog)
    llm_client = _create_reasoning_client(config)
    summary_service = DiagnosisSummaryService(client=llm_client, model=config.llm_model)
    diagnosis_service = IssueDiagnosisService(
        repository_catalog=catalog,
        probe_service=probe_service,
        summary_service=summary_service,
    )
    llm_service = LlmAnswerService(client=llm_client, model=config.llm_model)
    return MessageRouter(diagnosis_service=diagnosis_service, llm_answer_service=llm_service)


def create_feishu_client(config: BotConfig) -> FeishuBotClient:
    return FeishuBotClient(app_id=config.app_id, app_secret=config.app_secret)


def create_feishu_file_service(config: BotConfig) -> FeishuFileService:
    return FeishuFileService(app_id=config.app_id, app_secret=config.app_secret)


def create_resource_enrichment_service(config: BotConfig) -> ResourceEnrichmentService:
    return ResourceEnrichmentService(create_feishu_file_service(config), config.resource_cache_dir)
