function requiredEnv(env, name) {
  const value = env[name];
  if (!value || !value.trim()) {
    throw new Error(`缺少环境变量 ${name}`);
  }
  return value.trim();
}


function normalizeBaseUrl(value) {
  return value.replace(/\/+$/, '');
}


class DeepSeekClient {
  constructor({ env = process.env, httpClient = null } = {}) {
    this.env = env;
    this.httpClient = httpClient;
  }

  configuration() {
    return {
      provider: 'deepseek',
      model: this.env.DEEPSEEK_MODEL || 'deepseek-v4-flash',
      openaiBaseUrl: this.env.DEEPSEEK_OPENAI_BASE_URL || '',
      anthropicBaseUrl: this.env.DEEPSEEK_ANTHROPIC_BASE_URL || '',
      thinking: this.env.DEEPSEEK_THINKING || 'disabled',
      apiKeyConfigured: Boolean(this.env.DEEPSEEK_API_KEY),
    };
  }

  async chat(messages, options = {}) {
    const apiKey = requiredEnv(this.env, 'DEEPSEEK_API_KEY');
    const baseUrl = normalizeBaseUrl(requiredEnv(this.env, 'DEEPSEEK_OPENAI_BASE_URL'));
    const model = this.env.DEEPSEEK_MODEL || 'deepseek-v4-flash';
    const thinking = options.thinking || this.env.DEEPSEEK_THINKING || 'disabled';

    const httpClient = this.httpClient || require('axios');
    const response = await httpClient.post(
      `${baseUrl}/chat/completions`,
      {
        model,
        messages,
        temperature: options.temperature ?? 0.6,
        top_p: options.topP ?? 0.8,
        max_tokens: options.maxTokens ?? 1024,
        stream: false,
        thinking: { type: thinking },
      },
      {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
        },
        timeout: options.timeoutMs ?? 30000,
      },
    );

    const message = response.data?.choices?.[0]?.message;
    if (!message || typeof message.content !== 'string') {
      throw new Error('DeepSeek API 返回格式异常');
    }

    return {
      message,
      model: response.data.model || model,
      usage: response.data.usage || null,
      responseId: response.data.id || null,
    };
  }
}


function createDeepSeekClient(options) {
  return new DeepSeekClient(options);
}


module.exports = { DeepSeekClient, createDeepSeekClient };
