/*
 * CSRF protection helper (dependency-free).
 *
 * The server issues a per-session token and exposes it as
 *   <meta name="csrf-token" content="...">
 *
 * This script makes every state-changing request carry that token so the
 * server-side before_request check accepts it:
 *   1. Wraps window.fetch to add an X-CSRFToken header to same-origin,
 *      non-safe requests.
 *   2. Wraps XMLHttpRequest to do the same (covers jQuery/legacy XHR).
 *   3. Injects a hidden <input name="csrf_token"> into every non-GET <form>.
 *
 * Loaded early (before other scripts) in base.html and gamebase.html so the
 * fetch/XHR wrappers are installed before any request is made.
 */
(function () {
  "use strict";

  function getToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") : "";
  }

  var SAFE = /^(GET|HEAD|OPTIONS|TRACE)$/i;

  function sameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
      return true; // relative URL -> same origin
    }
  }

  // 1) Patch fetch ---------------------------------------------------------
  if (window.fetch) {
    var _fetch = window.fetch;
    window.fetch = function (input, init) {
      init = init || {};
      var isReq = typeof input !== "string" && input !== null && typeof input === "object";
      var method = (init.method || (isReq && input.method) || "GET").toUpperCase();
      var url = typeof input === "string" ? input : (isReq && input.url) || "";
      if (!SAFE.test(method) && sameOrigin(url)) {
        var headers = new Headers(init.headers || (isReq && input.headers) || {});
        if (!headers.has("X-CSRFToken")) {
          headers.set("X-CSRFToken", getToken());
        }
        init.headers = headers;
      }
      return _fetch.call(this, input, init);
    };
  }

  // 2) Patch XMLHttpRequest ------------------------------------------------
  var _open = XMLHttpRequest.prototype.open;
  var _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this._csrfMethod = method;
    this._csrfUrl = url;
    return _open.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    try {
      if (this._csrfMethod && !SAFE.test(this._csrfMethod) && sameOrigin(this._csrfUrl)) {
        this.setRequestHeader("X-CSRFToken", getToken());
      }
    } catch (e) {
      /* header may already be set; ignore */
    }
    return _send.apply(this, arguments);
  };

  // 3) Inject hidden field into forms -------------------------------------
  function injectForm(form) {
    if (!form || form.tagName !== "FORM") return;
    var method = (form.getAttribute("method") || "GET").toUpperCase();
    if (method === "GET") return;
    var existing = form.querySelector('input[name="csrf_token"]');
    if (existing) {
      existing.value = getToken();
      return;
    }
    var input = document.createElement("input");
    input.type = "hidden";
    input.name = "csrf_token";
    input.value = getToken();
    form.appendChild(input);
  }

  function injectAll() {
    var forms = document.querySelectorAll("form");
    for (var i = 0; i < forms.length; i++) injectForm(forms[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", injectAll);
  } else {
    injectAll();
  }

  // Safety net: ensure a token exists even on dynamically added forms.
  document.addEventListener(
    "submit",
    function (e) {
      injectForm(e.target);
    },
    true
  );
})();
