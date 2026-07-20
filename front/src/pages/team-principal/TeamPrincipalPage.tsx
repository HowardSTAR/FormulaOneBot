import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";

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
  const [data, setData] = useState<ConstructorPrincipalResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!constructorId) return;
    let cancelled = false;
    apiRequest<ConstructorPrincipalResponse>("/api/constructor-details", { constructorId, season })
      .then((response) => {
        if (cancelled) return;
        if (!response.principal?.photo_url) {
          setError("Карточка руководителя пока недоступна");
          return;
        }
        setData(response);
      })
      .catch(() => {
        if (!cancelled) setError("Не удалось загрузить руководителя команды");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [constructorId, season]);

  const backPath = `/constructor-details?constructorId=${encodeURIComponent(constructorId)}&season=${season}`;

  if (!constructorId) {
    return (
      <>
        <BackButton fallback="/constructors">← <span>Команды</span></BackButton>
        <div className="error">Не указана команда</div>
      </>
    );
  }

  if (loading) {
    return (
      <div className="loading full-width">
        <div className="spinner" />
        <div>Загрузка руководителя команды...</div>
      </div>
    );
  }

  if (error || !data?.principal) {
    return (
      <>
        <BackButton fallback={backPath}>← <span>Команда</span></BackButton>
        <div className="error">{error || "Карточка руководителя пока недоступна"}</div>
      </>
    );
  }

  const principal = data.principal;
  return (
    <>
      <article className="team-principal-mobile">
        <BackButton fallback={backPath}>← <span>{data.name}</span></BackButton>
        <div className="team-principal-hero">
          <img src={principal.photo_url} alt={principal.name} />
          <div className="team-principal-hero-copy">
            <span>{principal.role}</span>
            <h1>{principal.name}</h1>
            <p>{data.name} · сезон {season}</p>
          </div>
        </div>
        <section className="team-principal-bio">
          <h2>Краткая биография</h2>
          <p>{principal.bio || "Краткая биография пока недоступна."}</p>
          {principal.url && <a href={principal.url} target="_blank" rel="noopener noreferrer">Открыть источник →</a>}
        </section>
      </article>

      <article className="team-principal-desktop">
        <BackButton fallback={backPath}>← <span>{data.name}</span></BackButton>
        <header className="team-principal-desktop-hero">
          <div className="team-principal-desktop-photo">
            <img src={principal.photo_url} alt={principal.name} />
          </div>
          <div className="team-principal-desktop-copy">
            <span>{principal.role}</span>
            <h1>{principal.name}</h1>
            <div>
              <b>{data.name}</b>
              <b>Сезон {season}</b>
              {data.nationality && <b>{data.nationality}</b>}
            </div>
          </div>
        </header>
        <section className="team-principal-desktop-bio">
          <h2>Краткая биография</h2>
          <p>{principal.bio || "Краткая биография пока недоступна."}</p>
          {principal.url && <a href={principal.url} target="_blank" rel="noopener noreferrer">Открыть источник →</a>}
        </section>
      </article>
    </>
  );
}
