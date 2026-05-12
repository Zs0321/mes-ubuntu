from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FaqRule:
    keywords: tuple[str, ...]
    reply: str


FAQ_RULES: tuple[FaqRule, ...] = (
    FaqRule(
        keywords=("批量", "同步"),
        reply="如果要把手机本地缓存的多个项目配置一起刷新，建议在 APK 菜单里使用“批量同步当前所有项目”。它会按手机当前项目列表，逐个从服务器拉最新配置。",
    ),
    FaqRule(
        keywords=("batch", "sync"),
        reply="如果要一次刷新手机里的多个项目配置，建议使用“批量同步当前所有项目”。它会按本地项目列表逐个从服务器拉取最新配置。",
    ),
    FaqRule(
        keywords=("同步", "项目"),
        reply="同步项目时，优先使用“同步当前项目配置”或“批量同步当前所有项目”。前者适合刷新当前项目，后者适合把手机里已有项目的配置整体更新一遍。",
    ),
    FaqRule(
        keywords=("刷新", "项目"),
        reply="如果项目配置看起来还是旧的，可以先执行“同步当前项目配置”；如果不确定是哪个项目有问题，再执行“批量同步当前所有项目”。",
    ),
    FaqRule(
        keywords=("待复核",),
        reply="“待复核”表示系统拿到了记录或照片，但当前规则下还不能自动放行。常见原因是：缺少必需照片、QC 结果不满足放行条件、测试报告未关联，或者自动分析失败，需要人工确认。",
    ),
    FaqRule(
        keywords=("复核",),
        reply="“待复核”通常说明这条记录还不能自动放行，需要人工确认。你可以先检查照片、QC 结果、测试报告和质量放行规则是否都满足。",
    ),
    FaqRule(
        keywords=("401",),
        reply="HTTP 401 一般表示登录态失效、账号权限不足，或者请求没有带上有效 token。常见处理方式是重新登录，再确认当前账号是否有访问对应接口或功能页的权限。",
    ),
    FaqRule(
        keywords=("普通用户", "权限"),
        reply="普通用户默认不会开放管理员入口，所以看不到日志、用户管理、设置、项目管理这类功能是正常的。如果业务上确实需要，请让管理员调整账号角色或权限组。",
    ),
    FaqRule(
        keywords=("权限",),
        reply="如果提示权限不足，通常是当前账号不在允许的角色范围内。现在普通用户和管理员可见功能不同，像日志、用户管理、设置、项目管理这类入口通常只对管理员开放。",
    ),
    FaqRule(
        keywords=("照片", "上传", "失败"),
        reply="照片上传失败常见有三类原因：手机本地临时图片被删掉、网络或登录态异常、服务器端保存目录或权限异常。先看 APK 日志里是本地文件不存在、401，还是服务端 500，再分别处理。",
    ),
    FaqRule(
        keywords=("拍照", "失败"),
        reply="如果拍照后上传失败，先区分是“拍照失败”还是“上传后分析失败”。前者多半是本地文件或权限问题，后者更像网络、QC 服务或服务器端保存异常。",
    ),
    FaqRule(
        keywords=("你", "叫什么"),
        reply="我叫 MES小客服，是这套 MES 系统里的群聊助手，主要帮大家回答常见使用问题、查询统计结果和辅助排查异常。",
    ),
    FaqRule(
        keywords=("你", "来自哪里"),
        reply="我来自你们当前这套 MES 机器人能力，和 MES 服务部署在一起，专门服务现场使用答疑和数据查询。",
    ),
    FaqRule(
        keywords=("谁", "发明"),
        reply="我是你们这套 MES 项目里扩展出来的机器人能力，由 MES 的开发与运维一起做出来，专门帮现场提问和排查问题。",
    ),
    FaqRule(
        keywords=("你", "会做什么"),
        reply="我现在比较擅长回答常见 MES 问题、查询部分实时统计、辅助识别标签图片，以及帮大家做基础问题排查。",
    ),
)


class FaqService:
    def answer(self, text: str) -> str | None:
        content = self._normalize(text)
        if not content:
            return None

        for rule in FAQ_RULES:
            if all(keyword in content for keyword in rule.keywords):
                return rule.reply
        return None

    @staticmethod
    def _normalize(text: str) -> str:
        content = (text or "").strip().lower()
        if not content:
            return ""
        for old, new in (
            ("？", "?"),
            ("，", ","),
            ("。", "."),
            ("“", '"'),
            ("”", '"'),
            ("‘", "'"),
            ("’", "'"),
        ):
            content = content.replace(old, new)
        return content
