from __future__ import annotations
from .config import BotConfig
from .handlers.router import MessageRouter
from .services.dingtalk_doc_service import DingTalkDocService
from .services.dingtalk_image_service import DingTalkImageService
from .services.dingtalk_mes_user_resolver import DingTalkMesUserResolver
from .services.doc_action_service import DocActionService
from .services.faq_service import FaqService
from .services.hermes_api_service import HermesApiService
from .services.image_query_service import ImageQueryService
from .services.issue_diagnosis_service import IssueDiagnosisService
from .services.llm_answer_service import LlmAnswerService
from .services.mes_answer_service import MesAnswerService
from .services.mes_query_service import MesQueryService
from .services.openai_compatible_service import OpenAiCompatibleService
from .services.permission_query_service import PermissionQueryService
from .services.project_prefix_service import ProjectPrefixService
from .services.vision_recognition_service import VisionRecognitionService


def _resolve_text_model(config: BotConfig) -> str:
    if config.hermes_base_url.strip():
        return config.hermes_model.strip() or 'gpt-5.5'
    return config.text_model.strip()


def _create_text_client(config: BotConfig):
    model = _resolve_text_model(config)
    if config.hermes_base_url.strip():
        return HermesApiService(
            base_url=config.hermes_base_url,
            workspace=config.hermes_workspace,
            timeout=config.llm_timeout,
            default_model=model,
        )
    return OpenAiCompatibleService(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        timeout=config.llm_timeout,
    )


def create_router(config: BotConfig) -> MessageRouter:
    faq = FaqService()
    query = MesQueryService(
        config.mes_api_base_url,
        unified_db_path=config.unified_db_path,
        project_config_db_path=config.project_config_db_path,
    )
    mes = MesAnswerService(query)
    text_model = _resolve_text_model(config)
    text_client = _create_text_client(config)
    llm = LlmAnswerService(
        client=text_client,
        model=text_model,
    )
    vision_client = OpenAiCompatibleService(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        timeout=config.llm_timeout,
    )
    image_query = ImageQueryService(
        image_downloader=DingTalkImageService(
            client_id=config.client_id,
            client_secret=config.client_secret,
            robot_code=config.robot_code or config.client_id,
            timeout=config.llm_timeout,
        ),
        vision_service=VisionRecognitionService(
            client=vision_client,
            model=config.vision_model,
        ),
        prefix_service=ProjectPrefixService(config.project_config_db_path),
        mes_query_service=query,
    )
    permission_query = PermissionQueryService(
        prefix_service=image_query.prefix_service,
        user_resolver=DingTalkMesUserResolver(
            app_key=config.client_id,
            app_secret=config.client_secret,
            web_users_db_path=config.web_users_db_path,
            user_aliases_path=config.user_aliases_path,
            timeout=config.llm_timeout,
            api_base_url=config.dingtalk_api_base_url,
        ),
        project_config_db_path=config.project_config_db_path,
        web_users_db_path=config.web_users_db_path,
        image_downloader=image_query.image_downloader,
        vision_service=image_query.vision_service,
    )
    doc_action = DocActionService(
        mes_query_service=query,
        doc_service=DingTalkDocService(
            api_base_url=config.dingtalk_api_base_url,
            app_key=config.client_id,
            app_secret=config.client_secret,
            workspace_id=config.doc_workspace_id,
            parent_node_id=config.doc_parent_node_id,
            default_operator_id=config.doc_operator_id,
            state_path=config.doc_state_path,
            timeout=config.llm_timeout,
        ),
    )
    diagnosis = IssueDiagnosisService(
        probe_service=_LocalProbeService(),
        h2_db_path='/volume2/MES/QRMES/record/product_records.db',
        file_downloader=image_query.image_downloader,
    )
    return MessageRouter(faq, mes, llm, image_query, doc_action, permission_query, diagnosis)


class _LocalProbeService:
    def collect(self, targets: list[str]) -> dict:
        payload = {}
        for target in targets:
            payload[target] = {'health': [], 'scripts': [], 'files': []}
        return payload
