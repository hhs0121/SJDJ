from fastapi import FastAPI, Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, relationship
# 🚨 SQLAlchemy 추가 임포트
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from database import SessionLocal, engine, Base
from passlib.hash import bcrypt
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime
from pydantic import BaseModel
import uuid
import os
import requests
from bs4 import BeautifulSoup

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")

# 정적 파일 (CSS, 이미지 등) 서빙
app.mount("/static", StaticFiles(directory="static"), name="static")

# 템플릿 폴더 설정
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "static/news"
os.makedirs(UPLOAD_DIR, exist_ok=True)


GIMJE_NEWS_URL = "https://innovalley.smartfarmkorea.net/gimje/bbsArticle/list.do?bbsId=notice"
BASE_URL = "https://innovalley.smartfarmkorea.net/gimje/index.do"


# 🚨 모델 정의 (database.py의 Base를 사용)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)  # email 컬럼 추가
    password = Column(String(255))  # 해시 저장 공간
    role = Column(String(50))


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    username = Column(String(50), nullable=False)
    role = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)

    # 댓글과의 관계 정의: 게시글 삭제 시 댓글도 모두 삭제 (cascade)
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    username = Column(String(50), nullable=False)
    role = Column(String(50))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    # 게시글과의 관계 정의
    post = relationship("Post", back_populates="comments")


Base.metadata.create_all(bind=engine)  # 모든 모델의 테이블 생성


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



# -----------------------------------------------------------
# 홈 및 정적 페이지
# -----------------------------------------------------------

# 홈 페이지 (뉴스 목록 사용)
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = request.session.get("user")
    gimje_news = get_gimje_news()
    return templates.TemplateResponse("profile.html", {"request": request, "user": user,
                                                       "gimje_news": gimje_news,
                                                        })


# 실증단지 소개 페이지
@app.get("/about", response_class=HTMLResponse)
async def read_about(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("about.html", {"request": request, "user": user})


# 참여 안내 페이지
@app.get("/participate", response_class=HTMLResponse)
async def read_participate(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("participate.html", {"request": request, "user": user})


# 실시간 데이터 페이지
@app.get("/datas", response_class=HTMLResponse)
async def read_datas(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("datas.html", {"request": request, "user": user})


# 문의 페이지 (GET)
@app.get("/contact", response_class=HTMLResponse)
async def contact_form(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request})


# ai chat봇
@app.get("/aichat", response_class=HTMLResponse)
async def contact_form(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("aichat.html", {"request": request, "user": user})


@app.get("/imdae_sf", response_class=HTMLResponse)
async def contact_form(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("imdae_sf.html", {"request": request, "user": user})


# 문의 페이지 (POST)
@app.post("/contact", response_class=HTMLResponse)
async def submit_contact(request: Request, name: str = Form(...), email: str = Form(...), message: str = Form(...)):
    # 실제 환경에서는 DB 저장 또는 이메일 전송 처리 필요
    print(f"문의 도착: {name} | {email} | {message}")
    return templates.TemplateResponse("contact.html", {
        "request": request,
        "submitted": True,
        "name": name
    })


# -----------------------------------------------------------
# 인증 (Authentication)
# -----------------------------------------------------------

# 회원가입 GET
@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


# 🚨 회원가입 POST (비밀번호 해싱 및 에러 처리 수정)
@app.post("/register", response_class=HTMLResponse)
def register_user(
        request: Request,
        username: str = Form(...),
        email: str = Form(...),
        password: str = Form(...),
        role: str = Form(...),
        db: Session = Depends(get_db)
):
    existing = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if existing:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "이미 존재하는 아이디 또는 이메일입니다."}
        )

    # 비밀번호 해싱
    hashed_password = bcrypt.hash(password)

    new_user = User(
        username=username,
        # 해시된 비밀번호 저장
        password=hashed_password,
        email=email,
        role=role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return RedirectResponse(url="/login", status_code=302)


# 로그인 GET
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# 🚨 로그인 POST (비밀번호 검증 수정)
@app.post("/login", response_class=HTMLResponse)
def login_user(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()

    # user.password와 bcrypt.verify를 사용하여 비밀번호 검증
    if not user or not bcrypt.verify(password, user.password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "이메일 또는 비밀번호가 틀렸습니다."})

    request.session["user"] = {
        "username": user.username,
        "email": user.email,
        "role": user.role
    }
    return RedirectResponse(url="/", status_code=302)


# 로그아웃
@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


# -----------------------------------------------------------
# SNS (게시판) - DB 연동 완료
# -----------------------------------------------------------

# 글쓰기 페이지 (GET)
@app.get("/write", response_class=HTMLResponse)
def write_form(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("write.html", {"request": request, "user": user})


# 🚨 글쓰기 처리 (POST) - DB 사용
@app.post("/write", response_class=HTMLResponse)
def write_post(
        request: Request,
        title: str = Form(...),
        content: str = Form(...),
        db: Session = Depends(get_db)
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    new_post = Post(
        title=title,
        content=content,
        username=user["username"],
        role=user["role"],
        created_at=datetime.now()
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    return RedirectResponse(url="/sns", status_code=303)


# 🚨 게시글 목록 (`/sns` GET) - DB 사용
@app.get("/sns", response_class=HTMLResponse)
def board_page(request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")

    # DB에서 모든 게시글을 최신순으로 조회 (댓글 정보도 함께 로드)
    posts = db.query(Post).order_by(Post.created_at.desc()).all()

    # 댓글 수를 포함한 딕셔너리 리스트 생성
    posts_data = []
    for post in posts:
        posts_data.append({
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "username": post.username,
            "role": post.role,
            "created_at": post.created_at,
            "comment_count": len(post.comments)
        })

    return templates.TemplateResponse("sns.html", {
        "request": request,
        "user": user,
        "posts": posts_data
    })


# 🚨 게시글 상세 보기 (`/post/{post_id}` GET) - DB 사용
@app.get("/post/{post_id}", response_class=HTMLResponse)
def read_post(request: Request, post_id: int, db: Session = Depends(get_db)):
    user = request.session.get("user")

    # DB에서 게시글 조회
    post = db.query(Post).filter(Post.id == post_id).first()

    if not post:
        return HTMLResponse(content="게시글을 찾을 수 없습니다.", status_code=404)

    # 관계를 통해 댓글 목록을 가져옵니다. (최신순으로 정렬하는 것이 일반적)
    comments = db.query(Comment).filter(Comment.post_id == post_id).order_by(Comment.created_at.asc()).all()

    return templates.TemplateResponse("post_detail.html", {
        "request": request,
        "user": user,
        "post": post,
        "comments": comments
    })


# 🚨 댓글 쓰기 (`/comment/{post_id}` POST) - DB 사용
@app.post("/comment/{post_id}", response_class=HTMLResponse)
def write_comment(request: Request, post_id: int, content: str = Form(...), db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    new_comment = Comment(
        post_id=post_id,
        username=user["username"],
        role=user["role"],
        content=content,
        created_at=datetime.now()
    )

    db.add(new_comment)
    db.commit()

    return RedirectResponse(url=f"/post/{post_id}", status_code=303)


# 🚨 게시글 삭제 (`/delete/post/{post_id}`) - DB 사용
@app.get("/delete/post/{post_id}")
def delete_post(request: Request, post_id: int, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)

    # DB에서 게시글 조회
    post = db.query(Post).filter(Post.id == post_id).first()

    if not post:
        return HTMLResponse("게시글을 찾을 수 없습니다.", status_code=404)

    # 작성자만 삭제 가능
    if post.username != user["username"]:
        return HTMLResponse("권한이 없습니다.", status_code=403)

    # DB에서 삭제 (Post 모델에 cascade="all, delete-orphan" 설정으로 댓글 자동 삭제)
    db.delete(post)
    db.commit()

    return RedirectResponse("/sns", status_code=303)


# 🚨 댓글 삭제 (`/delete/comment/{post_id}/{comment_id}`) - DB 사용 (URL 경로 변경)
@app.get("/delete/comment/{post_id}/{comment_id}")
def delete_comment(request: Request, post_id: int, comment_id: int, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)

    # DB에서 댓글 조회
    comment = db.query(Comment).filter(Comment.id == comment_id, Comment.post_id == post_id).first()

    if not comment:
        return HTMLResponse("댓글을 찾을 수 없습니다.", status_code=404)

    # 작성자만 삭제 가능
    if comment.username != user["username"]:
        return HTMLResponse("댓글 삭제 권한이 없습니다.", status_code=403)

    # DB에서 삭제
    db.delete(comment)
    db.commit()

    return RedirectResponse(f"/post/{post_id}", status_code=303)


# -----------------------------------------------------------
# 뉴스 관련 (기존 코드 유지)
# -----------------------------------------------------------

# 🚨 뉴스 크롤링 함수
def get_gimje_news():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(GIMJE_NEWS_URL, timeout=10)  # 타임아웃 추가
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        rows = soup.select('.board_list tbody tr')

        gimje_news_list = []

        for row in rows:
            cols = row.find_all('td')

            if len(cols) >= 4:
                # 0: 번호, 1: 구분, 2: 제목, 3: 작성일, 4: 조회

                # 1. 제목 추출
                title_tag = cols[2].find('a')
                if not title_tag:
                    continue

                title = title_tag.text.strip()

                # 2. 링크 추출
                link = title_tag.get('href')
                full_link = BASE_URL + link

                # 3. 작성일 추출 (4번째 td, 인덱스 3)
                date = cols[3].text.strip()

                gimje_news_list.append({
                    "title": title,
                    "link": full_link,
                    "date": date
                })

        return gimje_news_list

    except requests.exceptions.RequestException as e:
        # 연결 오류, 타임아웃, 4xx/5xx HTTP 오류 등을 출력
        print(f"웹 크롤링 요청 오류 발생: {e}")
        return []  # 오류 발생 시 빈 리스트 반환
    except Exception as e:
        # 파싱 중 오류 발생 (셀렉터 오류 등)
        print(f"웹 파싱 오류 발생 (HTML 구조 확인 필요): {e}")
        return []


@app.get("/news", response_class=HTMLResponse)
def news_page(request: Request):
    user = request.session.get("user")

    gimje_news = get_gimje_news()

    # 기존 내부 news_list와 합치거나, gimje_news만 표시할 수 있습니다.

    return templates.TemplateResponse("news.html", {
        "request": request,
        "gimje_news": gimje_news,  # 김제 혁신밸리 뉴스
        "user": user
    })


# -----------------------------------------------------------
# 챗봇 관련 (기존 코드 유지)
# -----------------------------------------------------------

# --- 챗봇 입력 모델 ---
class ChatRequest(BaseModel):
    message: str


@app.post("/ask")
async def ask_chatbot(req: ChatRequest):
    user_input = req.message

    # 여기에 실제 ChatGPT API나 로직을 넣으면 됨
    # 지금은 테스트용 응답 예시
    reply = f" 챗봇 응답: '{user_input}'에 대한 답변이에요!"

    return JSONResponse({"reply": reply})


# uvicorn main:app --reload