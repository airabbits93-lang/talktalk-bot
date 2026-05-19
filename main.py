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
    """노션 페이지 내용 가져오기"""
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
    }
    async with httpx.AsyncClient() as client:
        # 블록 내용 가져오기
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
    """Claude API로 답변 생성"""
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-20250514",
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
    return data["content"][0]["text"]


async def send_talktalk_message(user_id: str, text: str):
    """네이버 톡톡으로 답변 전송"""
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
        await client.post(
            "https://talk.naver.com/v1/messages",
            headers=headers,
            json=body,
            timeout=10,
        )


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    event = data.get("event")
    user_id = data.get("user")

    # 톡톡 연결 확인용 (open 이벤트)
    if event == "open":
        await send_talktalk_message(user_id, "안녕하세요! 무엇이든 질문해주세요 😊")
        return JSONResponse({"success": True})

    # 메시지 수신
    if event == "send":
        text_content = data.get("textContent", {})
        user_message = text_content.get("text", "")

        if not user_message:
            return JSONResponse({"success": True})

        # 노션 매뉴얼 가져오기
        manual_text = await get_notion_content()

        # Claude로 답변 생성
        answer = await ask_claude(manual_text, user_message)

        # 톡톡으로 전송
        await send_talktalk_message(user_id, answer)

    return JSONResponse({"success": True})


@app.get("/")
async def health():
    return {"status": "ok", "message": "톡톡 챗봇 서버 실행 중!"}
