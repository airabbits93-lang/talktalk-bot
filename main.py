from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
import os

app = FastAPI()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID")
TALKTALK_ACCESS_TOKEN = os.environ.get("TALKTALK_ACCESS_TOKEN")


async def get_notion_content():
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
    }
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children",
            headers=headers
        )
        data = res.json()

    texts = []
    for block in data.get("results", []):
        btype = block.get("type")
        rich = block.get(btype, {}).get("rich_text", [])
        for r in rich:
            texts.append(r.get("plain_text", ""))

    return "\n".join(texts)


async def ask_claude(manual_text: str, user_message: str):
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1000,
        "system": f"""당신은 친절한 고객 상담 챗봇입니다.
아래 매뉴얼을 참고해서 고객 질문에 답변해주세요.
매뉴얼에 없는 내용은 '담당자에게 문의 부탁드립니다'라고 안내해주세요.

[매뉴얼]
{manual_text}""",
        "messages": [{"role": "user", "content": user_message}],
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
            timeout=30,
        )
    data = res.json()
    print("Claude API 응답:", data)  # 디버그용 로그
    
    if "content" not in data:
        error_msg = data.get("error", {}).get("message", "알 수 없는 오류")
        print("Claude API 오류:", error_msg)
        return f"일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    
    return data["content"][0]["text"]


async def send_talktalk_message(user_id: str, text: str):
    headers = {
        "Authorization": TALKTALK_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }
    body = {
        "event": "send",
        "user": user_id,
        "textContent": {"text": text},
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://talk.naver.com/v1/messages",
            headers=headers,
            json=body,
            timeout=10,
        )
    print("톡톡 전송 응답:", res.status_code)


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("톡톡 수신 데이터:", data)

    event = data.get("event")
    user_id = data.get("user")

    if event == "open":
        await send_talktalk_message(user_id, "안녕하세요! 무엇이든 질문해주세요 😊")
        return JSONResponse({"success": True})

    if event == "send":
        text_content = data.get("textContent", {})
        user_message = text_content.get("text", "")

        if not user_message:
            return JSONResponse({"success": True})

        manual_text = await get_notion_content()
        answer = await ask_claude(manual_text, user_message)
        await send_talktalk_message(user_id, answer)

    return JSONResponse({"success": True})


@app.get("/")
async def health():
    return {"status": "ok", "message": "톡톡 챗봇 서버 실행 중!"}
