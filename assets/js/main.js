// ===== 외부 채널 링크 — 여기만 수정하면 사이트 전체 버튼에 반영됩니다 =====
const LINKS = {
  store: "",      // 예: https://smartstore.naver.com/kingsbrewery
  kakao: "",      // 예: https://pf.kakao.com/_xxxxx
  instagram: "",  // 예: https://instagram.com/kingsbrewery
};

// 문의 폼 접수 주소 — Formspree(formspree.io) 무료 가입 후 받은 주소 입력
// 입력하면 문의가 대표님 이메일로 바로 도착합니다 (손님 메일 앱 불필요)
const FORM_ENDPOINT = ""; // 예: https://formspree.io/f/xxxxxxx

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

// ===== 개인정보 안내 =====
const privacy = document.getElementById("privacy");
const openPrivacy = () => { privacy.hidden = false; };
document.getElementById("privacyOpen").addEventListener("click", openPrivacy);
document.querySelectorAll("[data-privacy]").forEach((b) => b.addEventListener("click", openPrivacy));
document.getElementById("privacyClose").addEventListener("click", () => { privacy.hidden = true; });

// ===== 문의 폼 =====
document.getElementById("contactForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const note = document.getElementById("formNote");
  if (!FORM_ENDPOINT) {
    note.textContent = LINKS.kakao
      ? "온라인 접수 준비 중입니다. 카카오톡 채널로 문의해 주세요."
      : "온라인 접수 준비 중입니다. 전화로 문의해 주세요.";
    return;
  }
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  note.textContent = "전송 중입니다...";
  try {
    const res = await fetch(FORM_ENDPOINT, {
      method: "POST",
      body: new FormData(form),
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(res.status);
    form.reset();
    note.textContent = "문의가 접수되었습니다. 빠르게 연락드리겠습니다.";
  } catch (err) {
    note.textContent = "전송에 실패했습니다. 잠시 후 다시 시도하거나 전화로 문의해 주세요.";
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("year").textContent = new Date().getFullYear();
