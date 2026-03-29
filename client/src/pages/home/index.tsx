import { FileOutlined, HighlightOutlined, PlusOutlined, UnorderedListOutlined, UserOutlined } from "@ant-design/icons";
import { useList, useTranslate } from "@refinedev/core";
import { Card, Col, Row, Statistic, theme } from "antd";
import { Content } from "antd/es/layout/layout";
import Title from "antd/es/typography/Title";
import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import { ReactNode } from "react";
import { Trans } from "react-i18next";
import { Link, useNavigate } from "react-router";
import Logo from "../../icon.svg?react";
import { IFilament } from "../filaments/model";
import { ISpool } from "../spools/model";

dayjs.extend(utc);

const { useToken } = theme;

export const Home = () => {
  const { token } = useToken();
  const t = useTranslate();
  const navigate = useNavigate();

  const spools = useList<ISpool>({
    resource: "spool",
    pagination: { pageSize: 1 },
  });
  const filaments = useList<ISpool>({
    resource: "filament",
    pagination: { pageSize: 1 },
  });
  const vendors = useList<ISpool>({
    resource: "vendor",
    pagination: { pageSize: 1 },
  });

  const topFilaments = useList<IFilament>({
    resource: "filament",
    pagination: { pageSize: 10, current: 1 },
    sorters: [{ field: "total_remaining_weight", order: "desc" }],
  });

  const hasSpools = !spools.result || spools.result.data.length > 0;

  const ResourceStatsCard = (props: { loading: boolean; value: number; resource: string; icon: ReactNode }) => (
    <Col xs={12} md={6}>
      <Card
        loading={props.loading}
        actions={[
          <Link to={`/${props.resource}`} key="resource">
            <UnorderedListOutlined />
          </Link>,
          <Link to={`/${props.resource}/create`} key="create">
            <PlusOutlined />
          </Link>,
        ]}
      >
        <Statistic title={t(`${props.resource}.${props.resource}`)} value={props.value} prefix={props.icon} />
      </Card>
    </Col>
  );

  return (
    <Content
      style={{
        padding: "2em 20px",
        minHeight: 280,
        maxWidth: 800,
        margin: "0 auto",
        backgroundColor: token.colorBgContainer,
        borderRadius: token.borderRadiusLG,
        color: token.colorText,
        fontFamily: token.fontFamily,
        fontSize: token.fontSizeLG,
        lineHeight: 1.5,
      }}
    >
      <Title
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: token.fontSizeHeading1,
        }}
      >
        <div
          style={{
            display: "inline-block",
            height: "1.5em",
            marginRight: "0.5em",
          }}
        >
          <Logo />
        </div>
        Spoolman
      </Title>
      <Row justify="center" gutter={[16, 16]} style={{ marginTop: "3em" }}>
        <ResourceStatsCard
          resource="spool"
          value={spools.result?.total || 0}
          loading={spools.query.isLoading}
          icon={<FileOutlined />}
        />
        <ResourceStatsCard
          resource="filament"
          value={filaments.result?.total || 0}
          loading={filaments.query.isLoading}
          icon={<HighlightOutlined />}
        />
        <ResourceStatsCard
          resource="vendor"
          value={vendors.result?.total || 0}
          loading={vendors.query.isLoading}
          icon={<UserOutlined />}
        />
      </Row>
      {(() => {
        const items = (topFilaments.data?.data ?? []).filter(
          (f) => f.total_remaining_weight && f.total_remaining_weight > 0
        );
        const maxWeight = items.length > 0 ? Math.max(...items.map((f) => f.total_remaining_weight!)) : 1;

        return (
          items.length > 0 && (
            <Card
              style={{ marginTop: 24 }}
              loading={topFilaments.isLoading}
              title={t("home.top_filaments")}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {items.map((filament) => {
                  const weight = filament.total_remaining_weight!;
                  const pct = (weight / maxWeight) * 100;
                  const color = filament.color_hex ? `#${filament.color_hex}` : token.colorPrimary;
                  const label = filament.vendor?.name
                    ? `${filament.vendor.name} - ${filament.name ?? ""}`
                    : filament.name ?? `#${filament.id}`;

                  return (
                    <div
                      key={filament.id}
                      style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}
                      onClick={() => navigate(`/filament/show/${filament.id}`)}
                    >
                      <div
                        style={{
                          width: 140,
                          flexShrink: 0,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          fontSize: token.fontSizeSM,
                          textAlign: "right",
                        }}
                        title={label}
                      >
                        {label}
                      </div>
                      <div style={{ flex: 1, background: token.colorBgLayout, borderRadius: 4, height: 24 }}>
                        <div
                          style={{
                            width: `${pct}%`,
                            minWidth: 2,
                            height: "100%",
                            background: color,
                            borderRadius: 4,
                            transition: "width 0.3s ease",
                          }}
                        />
                      </div>
                      <div style={{ width: 60, flexShrink: 0, fontSize: token.fontSizeSM, textAlign: "right" }}>
                        {Math.round(weight)} g
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          )
        );
      })()}
      {!hasSpools && (
        <>
          <p style={{ marginTop: 32 }}>{t("home.welcome")}</p>
          <p>
            <Trans
              i18nKey="home.description"
              components={{
                helpPageLink: <Link to="/help" />,
              }}
            />
          </p>
        </>
      )}
    </Content>
  );
};

export default Home;
