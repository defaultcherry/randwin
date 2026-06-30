import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const appConfig = window.__APP_CONFIG__ || {};
const envHcaptchaSiteKey = import.meta.env.VITE_HCAPTCHA_SITE_KEY || '';

function getGiveawayIdFromPath() {
  const match = window.location.pathname.match(/^\/giveaways\/(\d+)$/);
  if (match) return match[1];
  const startParam = window.Telegram?.WebApp?.initDataUnsafe?.start_param || '';
  const startMatch = String(startParam).match(/^giveaway_(\d+)$/);
  if (startMatch) return startMatch[1];
  if (appConfig.giveawayId) return String(appConfig.giveawayId);
  return '';
}

function formatDuration(targetIso) {
  if (!targetIso) return '--';
  const target = new Date(targetIso).getTime();
  const diff = target - Date.now();
  if (diff <= 0) return '00:00:00';
  const total = Math.floor(diff / 1000);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const pad = (value) => String(value).padStart(2, '0');
  return days > 0 ? `${days}d ${pad(hours)}:${pad(minutes)}:${pad(seconds)}` : `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

function themeTelegram() {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;

  tg.ready();
  tg.expand();

  const theme = tg.themeParams || {};
  const root = document.documentElement.style;
  root.setProperty('--bg', theme.bg_color || '#0f1115');
  root.setProperty('--panel', theme.secondary_bg_color ? `${theme.secondary_bg_color}f2` : 'rgba(18, 20, 27, 0.92)');
  root.setProperty('--panel-2', theme.bg_color ? `${theme.bg_color}99` : 'rgba(255, 255, 255, 0.06)');
  root.setProperty('--text', theme.text_color || '#f3f5f7');
  root.setProperty('--muted', theme.hint_color || 'rgba(243, 245, 247, 0.7)');
  root.setProperty('--accent', theme.button_color || '#2ea6ff');
  root.setProperty('--accent-text', theme.button_text_color || '#ffffff');
  root.setProperty('--border', theme.hint_color ? `${theme.hint_color}22` : 'rgba(255, 255, 255, 0.08)');
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : { detail: await response.text() };
  if (!response.ok) {
    const error = new Error(payload.detail || 'Request failed');
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function Avatar({ item }) {
  const [failed, setFailed] = useState(false);
  if (item.avatar_url && !failed) {
    return <img className="avatar" src={item.avatar_url} alt={item.full_name} onError={() => setFailed(true)} />;
  }

  const initials = (item.full_name || 'U').trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() || '').join('') || 'U';
  return <div className="avatar avatar--fallback">{initials}</div>;
}

function App() {
  const giveawayId = getGiveawayIdFromPath();
  const initData = window.Telegram?.WebApp?.initData || '';
  const [loading, setLoading] = useState(Boolean(giveawayId));
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  const [mode, setMode] = useState('join');
  const [joinState, setJoinState] = useState('idle');
  const [captchaToken, setCaptchaToken] = useState('');
  const [tick, setTick] = useState(Date.now());
  const captchaRef = useRef(null);
  const captchaWidgetId = useRef(null);

  useEffect(() => { themeTelegram(); }, []);
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
      setError('');
      const payload = await fetchJson(`/api/giveaways/${giveawayId}`, {
        headers: { 'X-Telegram-Init-Data': initData },
      });
      setData(payload);
      setMode(payload.viewer_state === 'finished' ? 'results' : payload.viewer_state === 'already_joined' ? 'details' : 'join');
    } catch (err) {
      setError(err.message || 'Не удалось загрузить розыгрыш');
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
      if (!captchaRef.current || !(appConfig.hcaptchaSiteKey || envHcaptchaSiteKey)) return;
      if (!window.hcaptcha) {
        window.setTimeout(tryRender, 120);
        return;
      }
      if (captchaWidgetId.current !== null) return;
        captchaWidgetId.current = window.hcaptcha.render(captchaRef.current, {
        sitekey: appConfig.hcaptchaSiteKey || envHcaptchaSiteKey,
        callback: setCaptchaToken,
        'expired-callback': () => setCaptchaToken(''),
        'error-callback': () => setCaptchaToken(''),
      });
    };
    tryRender();
    return () => {
      alive = false;
      if (captchaWidgetId.current !== null && window.hcaptcha) {
        window.hcaptcha.reset(captchaWidgetId.current);
      }
      captchaWidgetId.current = null;
      setCaptchaToken('');
    };
  }, [data, mode]);

  async function handleJoin() {
    if (!captchaToken) {
      setError('Подтвердите капчу hCaptcha');
      return;
    }

    try {
      setJoinState('loading');
      setError('');
      const payload = await fetchJson(`/api/giveaways/${giveawayId}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initData, hcaptcha_token: captchaToken }),
      });
      setData((prev) => prev ? { ...prev, giveaway: payload.giveaway, viewer_state: 'already_joined' } : prev);
      setMode('details');
      setJoinState('success');
    } catch (err) {
      setJoinState('idle');
      setError(err.message || 'Не удалось подтвердить участие');
    }
  }

  function closeApp() {
    window.Telegram?.WebApp?.close();
  }

  const giveaway = data?.giveaway;
  const countdown = useMemo(() => giveaway ? formatDuration(giveaway.ends_at) : '--', [giveaway?.ends_at, tick]);
  const winners = giveaway?.winner_snapshots || [];

  if (!giveawayId) {
    return (
      <div className="mini-app">
        <div className="mini-app__surface">
          <section className="hero">
            <div className="hero__eyebrow">Telegram Mini App</div>
            <h1 className="hero__title">Откройте розыгрыш из Telegram</h1>
            <p className="hero__text">Страница открывается по кнопке в сообщении канала или из чата с ботом.</p>
          </section>
        </div>
      </div>
    );
  }

  if (loading) {
    return <div className="mini-app"><div className="mini-app__surface"><section className="card">Загрузка...</section></div></div>;
  }

  if (error && !data) {
    return (
      <div className="mini-app">
        <div className="mini-app__surface">
          <section className="card stack">
            <div className="status status--error">Ошибка</div>
            <div className="error">{error}</div>
            <div className="actions">
              <button className="button button--ghost" onClick={loadGiveaway}>Повторить</button>
              <button className="button button--danger" onClick={closeApp}>Закрыть</button>
            </div>
          </section>
        </div>
      </div>
    );
  }

  const statusLabel = giveaway.status === 'active' ? 'Розыгрыш активен' : giveaway.status === 'finished' ? 'Розыгрыш завершён' : 'Розыгрыш скоро начнётся';

  return (
    <div className="mini-app">
      <div className="mini-app__surface">
        <section className="hero">
          <div className="hero__eyebrow">Telegram Mini App</div>
          <h1 className="hero__title">{giveaway.title}</h1>
          <p className="hero__text">{giveaway.announcement_message}</p>
        </section>

        <section className="card stack">
          <div className={`status ${giveaway.status === 'active' ? 'status--active' : giveaway.status === 'finished' ? 'status--finished' : ''}`}>{statusLabel}</div>
          <div className="grid">
            <div className="metric"><div className="metric__label">Участников</div><div className="metric__value">{giveaway.participants_count}</div></div>
            <div className="metric"><div className="metric__label">Призовых мест</div><div className="metric__value">{giveaway.prize_places}</div></div>
            <div className="metric"><div className="metric__label">До итогов</div><div className="metric__value">{giveaway.status === 'finished' ? 'Готово' : countdown}</div></div>
            <div className="metric"><div className="metric__label">Канал</div><div className="metric__value">{giveaway.channel_title || giveaway.channel_username || giveaway.channel_id || '—'}</div></div>
          </div>
          <div className="actions">
            <button className="button button--ghost" onClick={() => setMode(mode === 'join' ? 'details' : 'join')}>{mode === 'join' ? 'Показать розыгрыш' : 'Вернуться к участию'}</button>
            <button className="button button--danger" onClick={closeApp}>Закрыть мини-апп</button>
          </div>
        </section>

        {mode === 'join'
          ? <JoinCard giveaway={giveaway} joinState={joinState} captchaRef={captchaRef} captchaToken={captchaToken} onJoin={handleJoin} onClose={closeApp} onOpenDetails={() => setMode('details')} viewerState={data.viewer_state} error={error} buttonColor={giveaway.button_color} />
          : <ResultsCard giveaway={giveaway} winners={winners} countdown={countdown} onBack={() => setMode('join')} />}
      </div>
    </div>
  );
}

function JoinCard({ giveaway, joinState, captchaRef, captchaToken, onJoin, onClose, onOpenDetails, viewerState, error, buttonColor }) {
  const alreadyJoined = viewerState === 'already_joined';
  const active = giveaway.status === 'active';

  if (giveaway.status === 'finished') {
    return (
      <section className="card stack">
        <div className="status status--finished">Розыгрыш завершён</div>
        <div className="message">Итоги подведены. Откройте результаты розыгрыша.</div>
        <div className="actions">
          <button className="button button--ghost" onClick={onClose}>Закрыть</button>
          <button className="button button--accent" style={{ background: buttonColor }} onClick={onOpenDetails}>Результаты</button>
        </div>
      </section>
    );
  }

  if (alreadyJoined) {
    return (
      <section className="card stack">
        <div className="status status--active">Вы уже участвуете</div>
        <div className="message">Ваше участие уже подтверждено. Можно закрыть мини-апп или открыть страницу розыгрыша.</div>
        <div className="actions">
          <button className="button button--ghost" onClick={onClose}>Закрыть мини-апп</button>
          <button className="button button--accent" style={{ background: buttonColor }} onClick={onOpenDetails}>Перейти к розыгрышу</button>
        </div>
      </section>
    );
  }

  return (
    <section className="card stack">
      <div className={active ? 'status status--active' : 'status'}>{active ? 'Подтвердите участие' : 'Ожидание старта'}</div>
      <div className="message">{active ? 'Пройдите hCaptcha и подтвердите подписку на канал.' : 'Розыгрыш ещё не начался.'}</div>
      {active ? <div ref={captchaRef} /> : null}
      {error ? <div className="error">{error}</div> : null}
      <div className="actions">
        <button className="button button--accent button--wide" style={{ background: buttonColor }} disabled={!active || !captchaToken || joinState === 'loading'} onClick={onJoin}>{joinState === 'loading' ? 'Проверяем...' : 'Участвовать'}</button>
        <button className="button button--ghost button--wide" onClick={onClose}>Закрыть мини-апп</button>
      </div>
    </section>
  );
}

function ResultsCard({ giveaway, winners, countdown, onBack }) {
  const finished = giveaway.status === 'finished';

  return (
    <section className="card stack">
      <div className={finished ? 'status status--finished' : 'status status--active'}>{finished ? 'Итоговый результат' : 'Страница розыгрыша'}</div>
      <div className="message">{finished ? 'Розыгрыш завершён. Ниже показаны победители.' : `До подведения итогов осталось ${countdown}.`}</div>
      {finished && winners.length ? (
        <div className="winner-list">
          {winners.map((item, index) => (
            <div key={`${item.telegram_id}-${index}`} className="winner-item">
              <Avatar item={item} />
              <div className="winner-item__body">
                <a className="winner-item__name" href={`tg://user?id=${item.telegram_id}`}>{item.full_name}</a>
                <div className="subtle">{item.username ? `@${item.username}` : 'Пользователь Telegram'}</div>
              </div>
            </div>
          ))}
        </div>
      ) : finished ? <div className="subtle">Победители не определены.</div> : null}
      <div className="actions">
        <button className="button button--ghost" onClick={onBack}>Назад</button>
        <button className="button button--danger" onClick={() => window.Telegram?.WebApp?.close()}>Закрыть</button>
      </div>
    </section>
  );
}

if (React && ReactDOM) {
  createRoot(document.getElementById('root')).render(<App />);
}
