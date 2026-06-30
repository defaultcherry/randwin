(function () {
  const React = window.React;
  const ReactDOM = window.ReactDOM;
  const h = React.createElement;
  const { useEffect, useMemo, useRef, useState } = React;

  function formatDuration(targetIso) {
    if (!targetIso) return "--";
    const target = new Date(targetIso).getTime();
    const diff = target - Date.now();

    if (diff <= 0) return "00:00:00";

    const total = Math.floor(diff / 1000);
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;

    const pad = (value) => String(value).padStart(2, "0");
    if (days > 0) {
      return `${days}d ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
    }
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  }

  function themeTelegram() {
    const tg = window.Telegram && window.Telegram.WebApp;
    if (!tg) return;

    tg.ready();
    tg.expand();

    const theme = tg.themeParams || {};
    const root = document.documentElement.style;
    root.setProperty("--bg", theme.bg_color || "#0f1115");
    root.setProperty("--panel", theme.secondary_bg_color ? `${theme.secondary_bg_color}f2` : "rgba(18, 20, 27, 0.92)");
    root.setProperty("--panel-2", theme.bg_color ? `${theme.bg_color}99` : "rgba(255, 255, 255, 0.06)");
    root.setProperty("--text", theme.text_color || "#f3f5f7");
    root.setProperty("--muted", theme.hint_color || "rgba(243, 245, 247, 0.7)");
    root.setProperty("--accent", theme.button_color || "#2ea6ff");
    root.setProperty("--accent-text", theme.button_text_color || "#ffffff");
    root.setProperty("--border", theme.hint_color ? `${theme.hint_color}22` : "rgba(255, 255, 255, 0.08)");
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : { detail: await response.text() };
    if (!response.ok) {
      const error = new Error(payload.detail || "Request failed");
      error.payload = payload;
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function App() {
    const giveawayId = window.__GIVEAWAY_ID__;
    const initData = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp.initData : "";
    const [loading, setLoading] = useState(Boolean(giveawayId));
    const [error, setError] = useState("");
    const [data, setData] = useState(null);
    const [mode, setMode] = useState("join");
    const [joinState, setJoinState] = useState("idle");
    const [captchaToken, setCaptchaToken] = useState("");
    const [tick, setTick] = useState(Date.now());
    const captchaRef = useRef(null);
    const captchaWidgetId = useRef(null);

    useEffect(() => {
      themeTelegram();
    }, []);

    useEffect(() => {
      const interval = window.setInterval(() => setTick(Date.now()), 1000);
      return () => window.clearInterval(interval);
    }, []);

    async function loadGiveaway() {
      if (!giveawayId) {
        setLoading(false);
        return;
      }

      try {
        setError("");
        const payload = await fetchJson(`/api/giveaways/${giveawayId}`, {
          headers: {
            "X-Telegram-Init-Data": initData,
          },
        });
        setData(payload);
        setMode(payload.viewer_state === "already_joined" || payload.viewer_state === "finished" ? "details" : "join");
      } catch (err) {
        setError(err.message || "Не удалось загрузить розыгрыш");
      } finally {
        setLoading(false);
      }
    }

    useEffect(() => {
      loadGiveaway();
      if (!giveawayId) return undefined;
      const poll = window.setInterval(loadGiveaway, 15000);
      return () => window.clearInterval(poll);
    }, [giveawayId]);

    useEffect(() => {
      let alive = true;

      const tryRender = () => {
        if (!alive) return;
        if (!captchaRef.current || !window.__HCAPTCHA_SITE_KEY__) return;
        if (!window.hcaptcha) {
          window.setTimeout(tryRender, 120);
          return;
        }

        if (captchaWidgetId.current !== null) return;

        captchaWidgetId.current = window.hcaptcha.render(captchaRef.current, {
          sitekey: window.__HCAPTCHA_SITE_KEY__,
          callback: setCaptchaToken,
          "expired-callback": () => setCaptchaToken(""),
          "error-callback": () => setCaptchaToken(""),
        });
      };

      tryRender();

      return () => {
        alive = false;
        if (captchaWidgetId.current !== null && window.hcaptcha) {
          window.hcaptcha.reset(captchaWidgetId.current);
        }
        captchaWidgetId.current = null;
        setCaptchaToken("");
      };
    }, [data, mode]);

    async function handleJoin() {
      if (!captchaToken) {
        setError("Подтвердите капчу hCaptcha");
        return;
      }

      try {
        setJoinState("loading");
        setError("");
        const payload = await fetchJson(`/api/giveaways/${giveawayId}/join`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            init_data: initData,
            hcaptcha_token: captchaToken,
          }),
        });
        setData((prev) => prev ? {
          ...prev,
          giveaway: payload.giveaway,
          viewer_state: "already_joined",
        } : prev);
        setMode("details");
        setJoinState("success");
      } catch (err) {
        setJoinState("idle");
        setError(err.message || "Не удалось подтвердить участие");
      }
    }

    function closeApp() {
      if (window.Telegram && window.Telegram.WebApp) {
        window.Telegram.WebApp.close();
      }
    }

    const giveaway = data && data.giveaway;
    const countdown = useMemo(() => {
      if (!giveaway) return "--";
      return formatDuration(giveaway.ends_at);
    }, [giveaway ? giveaway.ends_at : null, tick]);

    const winners = giveaway && giveaway.winner_ids ? giveaway.winner_ids : [];

    if (!giveawayId) {
      return h("div", { className: "mini-app" },
        h("div", { className: "mini-app__surface" },
          h("section", { className: "hero" },
            h("div", { className: "hero__eyebrow" }, "Telegram Mini App"),
            h("h1", { className: "hero__title" }, "Откройте розыгрыш из Telegram"),
            h("p", { className: "hero__text" }, "Эта страница открывается по кнопке в сообщении канала или из чата с ботом. Для теста используйте ссылку из Telegram Web App.")
          )
        )
      );
    }

    if (loading) {
      return h("div", { className: "mini-app" },
        h("div", { className: "mini-app__surface" },
          h("section", { className: "card" }, "Загрузка...")
        )
      );
    }

    if (error && !data) {
      return h("div", { className: "mini-app" },
        h("div", { className: "mini-app__surface" },
          h("section", { className: "card stack" },
            h("div", { className: "status status--error" }, "Ошибка"),
            h("div", { className: "error" }, error),
            h("div", { className: "actions" },
              h("button", { className: "button button--ghost", onClick: loadGiveaway }, "Повторить"),
              h("button", { className: "button button--danger", onClick: closeApp }, "Закрыть")
            )
          )
        )
      );
    }

    const statusLabel = giveaway.status === "active" ? "Розыгрыш активен" : giveaway.status === "finished" ? "Розыгрыш завершён" : "Розыгрыш скоро начнётся";

    return h("div", { className: "mini-app" },
      h("div", { className: "mini-app__surface" },
        h("section", { className: "hero" },
          h("div", { className: "hero__eyebrow" }, "Telegram Mini App"),
          h("h1", { className: "hero__title" }, giveaway.title),
          h("p", { className: "hero__text" }, giveaway.announcement_message)
        ),
        h("section", { className: "card stack" },
          h("div", { className: `status ${giveaway.status === 'active' ? 'status--active' : giveaway.status === 'finished' ? 'status--finished' : ''}` }, statusLabel),
          h("div", { className: "grid" },
            h("div", { className: "metric" }, h("div", { className: "metric__label" }, "Участников"), h("div", { className: "metric__value" }, giveaway.participants_count)),
            h("div", { className: "metric" }, h("div", { className: "metric__label" }, "Призовых мест"), h("div", { className: "metric__value" }, giveaway.prize_places)),
            h("div", { className: "metric" }, h("div", { className: "metric__label" }, "До итогов"), h("div", { className: "metric__value" }, giveaway.status === 'finished' ? 'Готово' : countdown)),
            h("div", { className: "metric" }, h("div", { className: "metric__label" }, "Страница"), h("div", { className: "metric__value" }, `#${giveaway.id}`))
          ),
          h("div", { className: "actions" },
            h("button", { className: "button button--ghost", onClick: () => setMode(mode === 'join' ? 'details' : 'join') }, mode === 'join' ? 'Показать розыгрыш' : 'Вернуться к участию'),
            h("button", { className: "button button--danger", onClick: closeApp }, "Закрыть мини-апп")
          )
        ),
        mode === "join"
          ? h(JoinCard, {
              giveaway,
              joinState,
              captchaRef,
              captchaToken,
              onJoin: handleJoin,
              onClose: closeApp,
              onOpenDetails: () => setMode("details"),
              viewerState: data.viewer_state,
              error,
              buttonColor: giveaway.button_color,
            })
          : h(DetailsCard, {
              giveaway,
              countdown,
              winners,
              onBack: () => setMode("join"),
            })
      )
    );
  }

  function JoinCard(props) {
    const { giveaway, joinState, captchaRef, captchaToken, onJoin, onClose, onOpenDetails, viewerState, error, buttonColor } = props;
    const alreadyJoined = viewerState === "already_joined";
    const active = giveaway.status === "active";

    if (giveaway.status === "finished") {
      return h("section", { className: "card stack" },
        h("div", { className: "status status--finished" }, "Розыгрыш завершён"),
        h("div", { className: "message" }, "Итоги подведены. Откройте страницу розыгрыша, чтобы посмотреть победителей."),
        h("div", { className: "actions" },
          h("button", { className: "button button--ghost", onClick: onClose }, "Закрыть"),
          h("button", { className: "button button--accent", onClick: onOpenDetails, style: { background: buttonColor } }, "Страница розыгрыша")
        )
      );
    }

    if (alreadyJoined) {
      return h("section", { className: "card stack" },
        h("div", { className: "status status--active" }, "Вы уже участвуете"),
        h("div", { className: "message" }, "Ваше участие уже подтверждено. Можете закрыть мини-апп или перейти на страницу розыгрыша."),
        h("div", { className: "actions" },
          h("button", { className: "button button--ghost", onClick: onClose }, "Закрыть мини-апп"),
          h("button", { className: "button button--accent", style: { background: buttonColor }, onClick: onOpenDetails }, "Перейти к розыгрышу")
        )
      );
    }

    return h("section", { className: "card stack" },
      h("div", { className: active ? "status status--active" : "status" }, active ? "Подтвердите участие" : "Ожидание старта"),
      h("div", { className: "message" }, active ? "Пройдите hCaptcha и подтвердите, что вы подписаны на канал." : "Розыгрыш ещё не начался. Вернитесь позже."),
      active ? h("div", { ref: captchaRef }) : null,
      error ? h("div", { className: "error" }, error) : null,
      h("div", { className: "actions" },
        h("button", {
          className: "button button--accent button--wide",
          style: { background: buttonColor },
          disabled: !active || !captchaToken || joinState === "loading",
          onClick: onJoin,
        }, joinState === "loading" ? "Проверяем..." : alreadyJoined ? "Участие подтверждено" : "Участвовать"),
        h("button", { className: "button button--ghost button--wide", onClick: onClose }, "Закрыть мини-апп")
      )
    );
  }

  function DetailsCard(props) {
    const { giveaway, countdown, winners, onBack } = props;
    const finished = giveaway.status === "finished";

    return h("section", { className: "card stack" },
      h("div", { className: finished ? "status status--finished" : "status status--active" }, finished ? "Итоговый результат" : "Страница розыгрыша"),
      h("div", { className: "message" }, finished ? "Розыгрыш завершён. Ниже показаны победители." : `До подведения итогов осталось ${countdown}.`),
      finished && winners.length
        ? h("div", { className: "winner-list" },
            winners.map((winnerId, index) => h("div", { key: `${winnerId}-${index}`, className: "winner-item" }, `Победитель #${index + 1}: ${winnerId}`))
          )
        : finished
          ? h("div", { className: "subtle" }, "Победители не определены.")
          : null,
      h("div", { className: "actions" },
        h("button", { className: "button button--ghost", onClick: onBack }, "Назад"),
        h("button", { className: "button button--danger", onClick: () => window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.close() }, "Закрыть")
      )
    );
  }

  if (!React || !ReactDOM) {
    document.body.innerHTML = '<div style="padding:20px;color:#fff">React is unavailable.</div>';
    return;
  }

  const root = ReactDOM.createRoot(document.getElementById("root"));
  root.render(h(App));
})();
