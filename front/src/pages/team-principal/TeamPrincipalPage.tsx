import { PageFeedback } from "../../components/PageFeedback";
import { cleanBiography } from "../../helpers/presentation";
import { nationalityLabel } from "../../constants/flags";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import "./team-principal.css";

type TeamPrincipal = {
  id: string;
  name: string;
  role: string;
  team_name: string;
  photo_url: string;
  bio: string;
  url: string;
};

type ConstructorPrincipalResponse = {
  constructorId: string;
  name: string;
  nationality: string;
  season: number;
  principal?: TeamPrincipal | null;
};

export default function TeamPrincipalPage() {
  const [searchParams] = useSearchParams();
  const constructorId = searchParams.get("constructorId") || "";
  const season = Number(searchParams.get("season")) || new Date().getFullYear();
  const [attempt, setAttempt] = useState(0);
  const requestKey = `${constructorId}:${season}:${attempt}`;
  const [result, setResult] = useState<{ key: string; data?: ConstructorPrincipalResponse; error?: string }>({ key: '' });
  const loading = result.key !== requestKey;
  const data = loading ? null : result.data;
  const error = loading ? '' : result.error;

  useEffect(() => {
    if (!constructorId) return;
    let cancelled = false;
    apiRequest<ConstructorPrincipalResponse>("/api/constructor-details", { constructorId, season })
      .then((response) => {
        if (cancelled) return;
        if (!response.principal?.photo_url) {
          setResult({ key: requestKey, error: "Карточка руководителя пока недоступна" });
          return;
        }
        setResult({ key: requestKey, data: response });
      })
      .catch(() => {
        if (!cancelled) setResult({ key: requestKey, error: "Не удалось загрузить руководителя команды" });
      });
    return () => { cancelled = true; };
  }, [constructorId, season, requestKey]);

  const backPath = `/constructor-details?constructorId=${encodeURIComponent(constructorId)}&season=${season}`;

  if (!constructorId) {
    return (
      <div className="team-principal">
        <BackButton fallback="/constructors">← <span>Команды</span></BackButton>
        <p className="team-principal-status" role="alert">Не указана команда</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="team-principal loading" role="status">
        <div className="spinner" aria-hidden="true" />
        <p className="team-principal-status">Загрузка руководителя команды…</p>
      </div>
    );
  }

  if (error || !data?.principal) {
    return (
      <div className="team-principal">
        <BackButton fallback={backPath}>← <span>Команда</span></BackButton>
        <PageFeedback message={error || "Карточка руководителя пока недоступна"} retry={() => setAttempt(v => v + 1)} parent={{to: backPath, label: "Карточка команды"}} />
      </div>
    );
  }

  const principal = data.principal;
  return (
    <article className="team-principal">
      <BackButton fallback={backPath} />
      <div className="team-principal-content">
        <header className="team-principal-heading">
          <h1>{principal.name}</h1>
          <p>{principal.role}</p>
          <p>{data.name} · сезон {season}</p>
          {data.nationality && <p>Страна команды: {nationalityLabel(data.nationality)}</p>}
        </header>
        <div className="team-principal-portrait">
          <img src={principal.photo_url} alt={principal.name} />
        </div>
        <section className="team-principal-bio">
          <h2>Краткая биография</h2>
          <p>{cleanBiography(principal.bio || "Краткая биография пока недоступна.")}</p>
          {principal.url && <a href={principal.url} target="_blank" rel="noopener noreferrer">Открыть источник →</a>}
        </section>
      </div>
    </article>
  );
}
