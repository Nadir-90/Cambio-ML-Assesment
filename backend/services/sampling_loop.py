import httpx
import platform
from enum import StrEnum
from typing import Any, cast
from datetime import datetime
from collections.abc import Callable
from backend.tools import ToolResult, ToolVersion
from backend.tools.schemas import BETA_FLAGS
from backend.tools.remote_collection import RemoteToolCollection
from anthropic import (
    AsyncAnthropic,
    AsyncAnthropicBedrock,
    AsyncAnthropicVertex,
    APIError,
    APIResponseValidationError,
    APIStatusError,
)
from anthropic.types.beta import (
    BetaCacheControlEphemeralParam,
    BetaContentBlockParam,
    BetaImageBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaTextBlock,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
)

PROMPT_CACHING_BETA_FLAG = "prompt-caching-2024-07-31"


class APIProvider(StrEnum):
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    VERTEX = "vertex"


def buildSystemPrompt(
    display_num: int | None = None, home_dir: str | None = None
) -> str:
    """Build the system prompt with the correct DISPLAY number and home directory."""
    dn = display_num if display_num is not None else 1
    hd = home_dir or "/home/computeruse"
    return f"""<SYSTEM_CAPABILITY>
* You are utilising an Ubuntu virtual machine using {platform.machine()} architecture with internet access.
* Your home directory is {hd}. All your files are stored there.
* You can feel free to install Ubuntu applications with your bash tool. Use curl instead of wget.
* There is a taskbar at the bottom of the screen with app launcher icons. To open Firefox, click the Firefox icon in the taskbar. To open a terminal, click the Terminal icon in the taskbar. These are the fastest ways to launch applications.
* firefox-esr is installed. If you need to open it with a specific URL, first open a terminal from the taskbar, then type: firefox-esr <url> &
* The bash tool is also available for non-GUI tasks (file operations, curl, python, etc.).
* When using your bash tool with commands that are expected to output very large quantities of text, redirect into a tmp file and use str_replace_based_edit_tool or `grep -n -B <lines before> -A <lines after> <query> <filename>` to confirm output.
* When viewing a page it can be helpful to zoom out so that you can see everything on the page.  Either that, or make sure you scroll down to see everything before deciding something isn't available.
* When using your computer function calls, they take a while to run and send back to you.  Where possible/feasible, try to chain multiple of these calls all into one function calls request.
* The current date is {datetime.today().strftime("%A, %B %-d, %Y")}.
</SYSTEM_CAPABILITY>

<IMPORTANT>
* When using Firefox, if a startup wizard appears, IGNORE IT.  Do not even click "skip this step".  Instead, click on the address bar where it says "Search or enter address", and enter the appropriate search term or URL there.
* If the item you are looking at is a pdf, if after taking a single screenshot of the pdf it seems that you want to read the entire document instead of trying to continue to read the pdf from your screenshots + navigation, determine the URL, use curl to download the pdf, install and use pdftotext to convert it to a text file, and then read that text file directly with your str_replace_based_edit_tool.
</IMPORTANT>"""


async def samplingLoop(
    *,
    model: str,
    provider: APIProvider,
    system_prompt_suffix: str,
    messages: list[BetaMessageParam],
    output_callback: Callable[[BetaContentBlockParam], None],
    tool_output_callback: Callable[[ToolResult, str], None],
    api_response_callback: Callable[
        [httpx.Request, httpx.Response | object | None, Exception | None], None
    ],
    api_key: str,
    only_n_most_recent_images: int | None = None,
    max_tokens: int = 4096,
    tool_version: ToolVersion,
    thinking_budget: int | None = None,
    token_efficient_tools_beta: bool = False,
    text_chunk_callback: Callable[[str], None] | None = None,
    display_num: int | None = None,
    home_dir: str | None = None,
    tool_server_url: str = "",
):
    """Agentic sampling loop for the assistant/tool interaction of computer use."""
    tool_collection = RemoteToolCollection(
        tool_server_url=tool_server_url,
        tool_version=tool_version,
    )
    prompt_text = buildSystemPrompt(display_num, home_dir)
    system = BetaTextBlockParam(
        type="text",
        text=f"{prompt_text}{' ' + system_prompt_suffix if system_prompt_suffix else ''}",
    )

    if provider == APIProvider.ANTHROPIC:
        client = AsyncAnthropic(api_key=api_key, max_retries=4)
    elif provider == APIProvider.VERTEX:
        client = AsyncAnthropicVertex()
    elif provider == APIProvider.BEDROCK:
        client = AsyncAnthropicBedrock()

    while True:
        enable_prompt_caching = False
        beta_flag = BETA_FLAGS.get(tool_version)
        betas = [beta_flag] if beta_flag else []
        if token_efficient_tools_beta:
            betas.append("token-efficient-tools-2025-02-19")
        image_truncation_threshold = only_n_most_recent_images or 0
        if provider == APIProvider.ANTHROPIC:
            enable_prompt_caching = True

        if enable_prompt_caching:
            betas.append(PROMPT_CACHING_BETA_FLAG)
            injectPromptCaching(messages)
            only_n_most_recent_images = 0
            system["cache_control"] = {"type": "ephemeral"}  # type: ignore

        if only_n_most_recent_images:
            filterRecentImages(
                messages,
                only_n_most_recent_images,
                min_removal_threshold=image_truncation_threshold,
            )

        extra_body = {}
        if thinking_budget:
            extra_body = {
                "thinking": {"type": "enabled", "budget_tokens": thinking_budget}
            }

        try:
            async with client.beta.messages.stream(
                max_tokens=max_tokens,
                messages=messages,
                model=model,
                system=[system],
                tools=tool_collection.toParams(),
                betas=betas,
                extra_body=extra_body,
            ) as stream:
                async for text in stream.text_stream:
                    if text_chunk_callback:
                        text_chunk_callback(text)
                response = await stream.get_final_message()
                api_response_callback(stream.response.request, stream.response, None)
        except (APIStatusError, APIResponseValidationError) as e:
            api_response_callback(e.request, e.response, e)
            return messages
        except APIError as e:
            api_response_callback(e.request, e.body, e)
            return messages
        response_params = responseToParams(response)
        messages.append({"role": "assistant", "content": response_params})

        tool_result_content: list[BetaToolResultBlockParam] = []
        for content_block in response_params:
            output_callback(content_block)
            if (
                isinstance(content_block, dict)
                and content_block.get("type") == "tool_use"
            ):
                tool_use_block = cast(BetaToolUseBlockParam, content_block)
                result = await tool_collection.run(
                    name=tool_use_block["name"],
                    tool_input=cast(dict[str, Any], tool_use_block.get("input", {})),
                )
                tool_result_content.append(
                    makeApiToolResult(result, tool_use_block["id"])
                )
                tool_output_callback(result, tool_use_block["id"])

        if not tool_result_content:
            return messages

        messages.append({"content": tool_result_content, "role": "user"})


def filterRecentImages(
    messages: list[BetaMessageParam],
    images_to_keep: int,
    min_removal_threshold: int,
):
    """Remove all but the most recent images from tool results to manage context size."""
    if images_to_keep is None:
        return messages

    tool_result_blocks = cast(
        list[BetaToolResultBlockParam],
        [
            item
            for message in messages
            for item in (
                message["content"] if isinstance(message["content"], list) else []
            )
            if isinstance(item, dict) and item.get("type") == "tool_result"
        ],
    )

    total_images = sum(
        1
        for tool_result in tool_result_blocks
        for content in tool_result.get("content", [])
        if isinstance(content, dict) and content.get("type") == "image"
    )

    images_to_remove = total_images - images_to_keep
    images_to_remove -= images_to_remove % min_removal_threshold

    for tool_result in tool_result_blocks:
        if isinstance(tool_result.get("content"), list):
            new_content = []
            for content in tool_result.get("content", []):
                if isinstance(content, dict) and content.get("type") == "image":
                    if images_to_remove > 0:
                        images_to_remove -= 1
                        continue
                new_content.append(content)
            tool_result["content"] = new_content


def responseToParams(
    response: BetaMessage,
) -> list[BetaContentBlockParam]:
    """Convert a BetaMessage response into a list of content block params."""
    res: list[BetaContentBlockParam] = []
    for block in response.content:
        if isinstance(block, BetaTextBlock):
            if block.text:
                res.append(BetaTextBlockParam(type="text", text=block.text))
            elif getattr(block, "type", None) == "thinking":
                thinking_block = {
                    "type": "thinking",
                    "thinking": getattr(block, "thinking", None),
                }
                if hasattr(block, "signature"):
                    thinking_block["signature"] = getattr(block, "signature", None)
                res.append(cast(BetaContentBlockParam, thinking_block))
        else:
            res.append(cast(BetaToolUseBlockParam, block.model_dump()))
    return res


def injectPromptCaching(
    messages: list[BetaMessageParam],
):
    """Set cache breakpoints for the 3 most recent turns."""
    breakpoints_remaining = 3
    for message in reversed(messages):
        if message["role"] == "user" and isinstance(
            content := message["content"], list
        ):
            if breakpoints_remaining:
                breakpoints_remaining -= 1
                content[-1]["cache_control"] = BetaCacheControlEphemeralParam(  # type: ignore
                    {"type": "ephemeral"}
                )
            else:
                if isinstance(content[-1], dict) and "cache_control" in content[-1]:
                    del content[-1]["cache_control"]  # type: ignore
                break


def makeApiToolResult(result: ToolResult, tool_use_id: str) -> BetaToolResultBlockParam:
    """Convert an agent ToolResult to an API ToolResultBlockParam."""
    tool_result_content: list[BetaTextBlockParam | BetaImageBlockParam] | str = []
    is_error = False
    if result.error:
        is_error = True
        tool_result_content = prependSystemResult(result, result.error)
    else:
        if result.output:
            tool_result_content.append(
                {
                    "type": "text",
                    "text": prependSystemResult(result, result.output),
                }
            )
        if result.base64_image:
            tool_result_content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": result.base64_image,
                    },
                }
            )
    return {
        "type": "tool_result",
        "content": tool_result_content,
        "tool_use_id": tool_use_id,
        "is_error": is_error,
    }


def prependSystemResult(result: ToolResult, result_text: str):
    """Prepend system tool result text if present."""
    if result.system:
        result_text = f"<system>{result.system}</system>\n{result_text}"
    return result_text
