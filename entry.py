#!/usr/bin/env python3
"""image-analyzer-mcp: MCP server for AI-powered image analysis."""

import json
import sys
import httpx

API_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
API_KEY = "tp-c6w5jsmi9x28pgwhuq8gh9bshuib12qx7f3brwc80orthn51"
MODEL = "mimo-v2.5-pro"


def send_mcp_response(result, request_id=None):
    """Send a JSON-RPC response back to the MCP client."""
    response = {"jsonrpc": "2.0", "result": result}
    if request_id is not None:
        response["id"] = request_id
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def send_mcp_error(code, message, request_id=None):
    """Send a JSON-RPC error response."""
    error = {"jsonrpc": "2.0", "error": {"code": code, "message": message}}
    if request_id is not None:
        error["id"] = request_id
    sys.stdout.write(json.dumps(error, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def analyze_image(image_url: str, prompt: str = "描述这张图片") -> str:
    """
    Download an image from a URL and analyze it using the MiMo vision API.
    
    Args:
        image_url: URL of the image to analyze
        prompt: Analysis prompt (default: "描述这张图片")
    
    Returns:
        Analysis result text from the AI model
    """
    try:
        with httpx.Client(timeout=30.0, verify=True) as client:
            # First, download the image to verify it's accessible
            img_resp = client.get(image_url, timeout=15.0)
            img_resp.raise_for_status()
            content_type = img_resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                return f"错误：URL 返回的不是图片 (Content-Type: {content_type})"

        # Now call MiMo API with the image URL
        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        }

        headers = {
            "api-key": API_KEY,
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=60.0, verify=True) as client:
            resp = client.post(API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # Extract assistant message content
        choices = data.get("choices", [])
        if not choices:
            return "错误：API 响应中没有 choices"
        message = choices[0].get("message", {})
        content = message.get("content", "")
        return content if content else "错误：API 返回了空内容"

    except httpx.HTTPStatusError as e:
        return f"HTTP 错误 {e.response.status_code}: {e.response.text[:500]}"
    except httpx.RequestError as e:
        return f"网络请求失败: {str(e)}"
    except Exception as e:
        return f"分析图片时出错: {str(e)}"


def process_request(request):
    """Process a JSON-RPC request."""
    req_id = request.get("id")
    method = request.get("method", "")

    if method == "initialize":
        send_mcp_response(
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {
                        "image_analyzer": {
                            "name": "image_analyzer",
                            "description": "智能分析图片内容，支持OCR文字识别、物体检测、场景描述。输入图片URL，AI会自动分析并返回详细描述。",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "image_url": {
                                        "type": "string",
                                        "description": "图片的URL地址（必须是可直接访问的图片链接）"
                                    },
                                    "prompt": {
                                        "type": "string",
                                        "description": "分析提示词，默认为'描述这张图片'。可以改为'识别图片中的文字'、'检测图片中的物体'等",
                                        "default": "描述这张图片"
                                    }
                                },
                                "required": ["image_url"]
                            }
                        }
                    }
                },
                "serverInfo": {
                    "name": "image-analyzer-mcp",
                    "version": "1.0.0"
                }
            },
            req_id,
        )

    elif method == "listTools":
        send_mcp_response(
            {
                "tools": [
                    {
                        "name": "image_analyzer",
                        "description": "智能分析图片内容，支持OCR文字识别、物体检测、场景描述。输入图片URL，AI会自动分析并返回详细描述。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "image_url": {
                                    "type": "string",
                                    "description": "图片的URL地址（必须是可直接访问的图片链接）"
                                },
                                "prompt": {
                                    "type": "string",
                                    "description": "分析提示词，默认为'描述这张图片'。可以改为'识别图片中的文字'、'检测图片中的物体'等",
                                    "default": "描述这张图片"
                                }
                            },
                            "required": ["image_url"]
                        }
                    }
                ]
            },
            req_id,
        )

    elif method == "callTool":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "image_analyzer":
            image_url = arguments.get("image_url", "")
            prompt = arguments.get("prompt", "描述这张图片")
            if not image_url:
                send_mcp_error(-32602, "缺少必要参数: image_url", req_id)
                return
            result = analyze_image(image_url, prompt)
            send_mcp_response({"content": [{"type": "text", "text": result}]}, req_id)
        else:
            send_mcp_error(-32601, f"未知工具: {tool_name}", req_id)

    elif method == "ping":
        send_mcp_response({}, req_id)

    elif method == "notifications/initialized":
        # No response needed for notifications
        pass

    else:
        send_mcp_error(-32601, f"未知方法: {method}", req_id)


def main():
    """Main entry point - read JSON-RPC requests from stdin."""
    buffer = ""
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                process_request(request)
            except json.JSONDecodeError as e:
                send_mcp_error(-32700, f"JSON 解析错误: {str(e)}")
        except EOFError:
            break
        except KeyboardInterrupt:
            break
        except Exception as e:
            send_mcp_error(-32603, f"内部错误: {str(e)}")


if __name__ == "__main__":
    main()
