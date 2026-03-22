import { useTranslate } from "@refinedev/core";
import { Alert, Button, Checkbox, Divider, Form, Input, message, Radio, Select, Typography } from "antd";
import { useEffect } from "react";
import { useGetSettings, useSetSetting } from "../../utils/querySettings";
import { useGetPrinters } from "../../utils/queryPrinter";

export function GeneralSettings() {
  const settings = useGetSettings();
  const setBaseUrl = useSetSetting("base_url");
  const setCurrency = useSetSetting("currency");
  const setRoundPrices = useSetSetting("round_prices");
  const setPrintMode = useSetSetting("print_mode");
  const setHostPrinterName = useSetSetting("host_printer_name");
  const setHostPrinterOptions = useSetSetting("host_printer_options");
  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();
  const t = useTranslate();

  const printersQuery = useGetPrinters();
  const printMode = settings.data ? JSON.parse(settings.data.print_mode?.value ?? '"browser"') : "browser";

  // Set initial form values
  useEffect(() => {
    if (settings.data) {
      form.setFieldsValue({
        currency: JSON.parse(settings.data.currency.value),
        base_url: JSON.parse(settings.data.base_url.value),
        round_prices: JSON.parse(settings.data.round_prices.value),
        print_mode: JSON.parse(settings.data.print_mode?.value ?? '"browser"'),
        host_printer_name: JSON.parse(settings.data.host_printer_name?.value ?? '""'),
        host_printer_options: JSON.stringify(
          JSON.parse(settings.data.host_printer_options?.value ?? '{}'),
          null,
          2
        ),
      });
    }
  }, [settings.data, form]);

  // Popup message if setSetting is successful
  useEffect(() => {
    if (setCurrency.isSuccess) {
      messageApi.success(t("notifications.saveSuccessful"));
    }
  }, [setCurrency.isSuccess, messageApi, t]);

  // Handle form submit
  const onFinish = (values: {
    currency: string;
    base_url: string;
    round_prices: boolean;
    print_mode: string;
    host_printer_name: string;
    host_printer_options: string;
  }) => {
    // Check if the currency has changed
    if (settings.data?.currency.value !== JSON.stringify(values.currency)) {
      setCurrency.mutate(values.currency);
    }
    // Check if the base URL has changed
    if (settings.data?.base_url.value !== JSON.stringify(values.base_url)) {
      setBaseUrl.mutate(values.base_url);
    }

    // Check if the setting to round prices has changed
    if (settings.data?.round_prices.value !== JSON.stringify(values.round_prices)) {
      setRoundPrices.mutate(values.round_prices);
    }

    // Print mode
    if (settings.data?.print_mode?.value !== JSON.stringify(values.print_mode)) {
      setPrintMode.mutate(values.print_mode);
    }

    // Host printer name
    if (settings.data?.host_printer_name?.value !== JSON.stringify(values.host_printer_name)) {
      setHostPrinterName.mutate(values.host_printer_name ?? "");
    }

    // Host printer options
    if (values.host_printer_options) {
      try {
        const opts = JSON.parse(values.host_printer_options);
        if (settings.data?.host_printer_options?.value !== JSON.stringify(opts)) {
          setHostPrinterOptions.mutate(opts);
        }
      } catch {
        messageApi.error(t("settings.general.printer_options.invalidJson"));
      }
    }
  };

  return (
    <>
      <Form
        form={form}
        labelCol={{ span: 8 }}
        wrapperCol={{ span: 16 }}
        initialValues={{
          currency: settings.data?.currency.value,
          round_prices: settings.data?.round_prices.value,
          base_url: settings.data?.base_url.value,
          print_mode: "browser",
          host_printer_name: "",
          host_printer_options: "{}",
        }}
        onFinish={onFinish}
        style={{
          maxWidth: "600px",
          margin: "0 auto",
        }}
      >
        <Form.Item
          label={t("settings.general.currency.label")}
          name="currency"
          rules={[
            {
              required: true,
            },
            {
              pattern: /^[A-Z]{3}$/,
            },
          ]}
        >
          <Input />
        </Form.Item>

        <Form.Item
          label={t("settings.general.base_url.label")}
          tooltip={t("settings.general.base_url.tooltip")}
          name="base_url"
          rules={[
            {
              required: false,
            },
            {
              pattern: /^https?:\/\/.+(?<!\/)$/,
            },
          ]}
        >
          <Input placeholder="https://example.com:8000" />
        </Form.Item>

        <Form.Item
          label={t("settings.general.round_prices.label")}
          tooltip={t("settings.general.round_prices.tooltip")}
          name="round_prices"
          valuePropName="checked"
        >
          <Checkbox />
        </Form.Item>

        <Divider>{t("settings.general.printing.title")}</Divider>

        <Form.Item
          label={t("settings.general.print_mode.label")}
          tooltip={t("settings.general.print_mode.tooltip")}
          name="print_mode"
        >
          <Radio.Group>
            <Radio value="browser">{t("settings.general.print_mode.browser")}</Radio>
            <Radio value="host">{t("settings.general.print_mode.host")}</Radio>
          </Radio.Group>
        </Form.Item>

        {printMode === "host" && (
          <>
            {printersQuery.data && !printersQuery.data.cups_available && (
              <Form.Item wrapperCol={{ offset: 8, span: 16 }}>
                <Alert
                  type="warning"
                  message={t("settings.general.cups_not_available")}
                  showIcon
                />
              </Form.Item>
            )}

            <Form.Item
              label={t("settings.general.host_printer.label")}
              tooltip={t("settings.general.host_printer.tooltip")}
              name="host_printer_name"
            >
              <Select
                allowClear
                placeholder={t("settings.general.host_printer.placeholder")}
                loading={printersQuery.isLoading}
              >
                {printersQuery.data?.printers.map((printer) => (
                  <Select.Option key={printer.name} value={printer.name}>
                    {printer.name}
                    {printer.is_default ? ` (${t("settings.general.host_printer.default")})` : ""}
                    {` — ${printer.status}`}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>

            <Form.Item
              label={t("settings.general.printer_options.label")}
              tooltip={t("settings.general.printer_options.tooltip")}
              name="host_printer_options"
              rules={[
                {
                  validator: (_, value) => {
                    if (!value || value.trim() === "") return Promise.resolve();
                    try {
                      JSON.parse(value);
                      return Promise.resolve();
                    } catch {
                      return Promise.reject(new Error(t("settings.general.printer_options.invalidJson")));
                    }
                  },
                },
              ]}
            >
              <Input.TextArea
                rows={3}
                placeholder='{"media": "Custom.62x29mm", "fit-to-page": ""}'
              />
            </Form.Item>
          </>
        )}

        <Form.Item wrapperCol={{ offset: 8, span: 16 }}>
          <Button type="primary" htmlType="submit" loading={settings.isFetching || setCurrency.isPending}>
            {t("buttons.save")}
          </Button>
        </Form.Item>
      </Form>
      {contextHolder}
    </>
  );
}
