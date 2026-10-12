// ===== 링크 설정 — 주소만 넣으면 사이트 전체 버튼에 반영됩니다 =====
// 판매는 네이버 스마트스토어로 통일. 상품 주소가 비면 스마트스토어 메인으로 연결.
const LINKS = {
  store: "", // 스마트스토어 메인       예: https://smartstore.naver.com/kingsbrewery
  gb17: "",  // 금배주 17도 상품 주소
  gb25: "",  // 금배주 25도 상품 주소
  gb40: "",  // 금배주 40도 상품 주소
  kakao: "", // 카카오톡 채널
  blog: "",  // 네이버 블로그
  wadiz: "", // 봉신설주 와디즈 페이지
  terms: "",   // 이용약관 페이지 (아임웹 기본 약관 주소)
  privacy: "", // 개인정보처리방침 페이지
};
const FALLBACK = { gb17: "store", gb25: "store", gb40: "store" };

document.querySelectorAll("[data-link]").forEach((a) => {
  const key = a.dataset.link;
  const url = LINKS[key] || LINKS[FALLBACK[key]];
  if (url) {
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener";
  } else {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      alert("준비 중입니다. 033-672-2888 로 문의해 주세요.");
    });
  }
});

// ===== 성인 확인 (메인) =====
const gate = document.getElementById("ageGate");
if (gate) {
  let verified = false;
  try { verified = localStorage.getItem("kings_age_ok") === "1"; } catch (e) {}
  if (!verified) {
    gate.hidden = false;
    document.body.style.overflow = "hidden";
  }
  document.getElementById("ageYes").addEventListener("click", () => {
    try { localStorage.setItem("kings_age_ok", "1"); } catch (e) {}
    gate.hidden = true;
    document.body.style.overflow = "";
  });
}

// ===== 헤더: 첫 화면에서는 플럼, 스크롤하면 아이보리 =====
const header = document.getElementById("header");
if (header && !header.classList.contains("is-fixed")) {
  const onScroll = () => header.classList.toggle("is-light", window.scrollY > window.innerHeight * 0.6);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
}

// ===== 모바일 메뉴 =====
const burger = document.getElementById("burger");
const nav = document.getElementById("nav");
if (burger && nav) {
  burger.addEventListener("click", () => {
    const open = nav.classList.toggle("is-open");
    burger.setAttribute("aria-expanded", open);
  });
  nav.querySelectorAll("a").forEach((a) =>
    a.addEventListener("click", () => {
      nav.classList.remove("is-open");
      burger.setAttribute("aria-expanded", "false");
    })
  );
}

// ===== 시음 리뷰 폼 (시안 — 실제 접수는 아임웹 입력폼) =====
const reviewForm = document.getElementById("reviewForm");
if (reviewForm) {
  reviewForm.addEventListener("submit", (e) => {
    e.preventDefault();
    document.getElementById("done").textContent =
      "시안 화면입니다. 실제 접수는 아임웹 입력폼으로 연결됩니다.";
  });
}

const year = document.getElementById("year");
if (year) year.textContent = new Date().getFullYear();
