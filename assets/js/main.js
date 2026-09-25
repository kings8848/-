// ===== 외부 채널 링크 — 여기만 수정하면 사이트 전체 버튼에 반영됩니다 =====
const LINKS = {
  store: "",      // 예: https://smartstore.naver.com/kingsbrewery
  kakao: "",      // 예: https://pf.kakao.com/_xxxxx
  instagram: "",  // 예: https://instagram.com/kingsbrewery
};

// 문의 폼 수신 이메일 (폼 제출 시 메일 앱으로 연결)
const CONTACT_EMAIL = ""; // 예: hello@kingsbrewery.kr

document.querySelectorAll("[data-link]").forEach((a) => {
  const url = LINKS[a.dataset.link];
  if (url) {
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener";
  } else {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      alert("준비 중입니다. 문의 폼 또는 전화로 연락 주세요.");
    });
  }
});

// ===== 성인 인증 =====
const gate = document.getElementById("ageGate");
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

// ===== 모바일 메뉴 =====
const toggle = document.getElementById("navToggle");
const nav = document.getElementById("nav");
toggle.addEventListener("click", () => {
  const open = nav.classList.toggle("is-open");
  toggle.setAttribute("aria-expanded", open);
});
nav.querySelectorAll("a").forEach((a) =>
  a.addEventListener("click", () => {
    nav.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
  })
);

// ===== 문의 폼 =====
document.getElementById("contactForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const note = document.getElementById("formNote");
  if (!CONTACT_EMAIL) {
    note.textContent = "수신 이메일이 아직 설정되지 않았습니다. 전화로 문의 부탁드립니다.";
    return;
  }
  const subject = `[킹스양조장 문의] ${f.get("type")} - ${f.get("name")}`;
  const body = `이름/회사: ${f.get("name")}\n연락처: ${f.get("phone")}\n유형: ${f.get("type")}\n\n${f.get("message")}`;
  location.href = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  note.textContent = "메일 앱이 열립니다. 전송을 눌러 주세요.";
});

document.getElementById("year").textContent = new Date().getFullYear();
