// ===== 링크 설정 — 주소만 넣으면 사이트 전체 버튼에 반영됩니다 =====
// 판매는 네이버 스마트스토어로 통일합니다.
// 상품별 주소(gb17·gb25·gb40)가 비어 있으면 스마트스토어 메인(store)으로 연결됩니다.
const LINKS = {
  store: "", // 스마트스토어 메인    예: https://smartstore.naver.com/kingsbrewery
  gb17: "",  // 금배주 17도 상품 주소 예: https://smartstore.naver.com/kingsbrewery/products/0000000000
  gb25: "",  // 금배주 25도 상품 주소
  gb40: "",  // 금배주 40도 상품 주소
  kakao: "", // 카카오톡 채널        예: https://pf.kakao.com/_xxxxx
  blog: "",  // 네이버 블로그        예: https://blog.naver.com/xxxxx
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

// ===== 성인 확인 =====
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

document.getElementById("year").textContent = new Date().getFullYear();
