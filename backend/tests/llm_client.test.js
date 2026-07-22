const assert = require('assert');
const { createDeepSeekClient } = require('../llm_client');


async function testOpenAICompatibleRequestContract() {
  let captured;
  const httpClient = {
    post: async (...args) => {
      captured = args;
      return {
        data: {
          id: 'chat-test',
          model: 'deepseek-v4-flash',
          choices: [{ message: { role: 'assistant', content: '测试成功' } }],
          usage: { prompt_tokens: 10, completion_tokens: 2, total_tokens: 12 },
        },
      };
    },
  };
  const client = createDeepSeekClient({
    httpClient,
    env: {
      DEEPSEEK_API_KEY: 'test-key',
      DEEPSEEK_OPENAI_BASE_URL: 'https://provider.example/v1/',
      DEEPSEEK_ANTHROPIC_BASE_URL: 'https://provider.example/anthropic',
      DEEPSEEK_MODEL: 'deepseek-v4-flash',
      DEEPSEEK_THINKING: 'disabled',
    },
  });

  const result = await client.chat([{ role: 'user', content: '你好' }]);

  assert.strictEqual(captured[0], 'https://provider.example/v1/chat/completions');
  assert.strictEqual(captured[1].model, 'deepseek-v4-flash');
  assert.deepStrictEqual(captured[1].thinking, { type: 'disabled' });
  assert.strictEqual(captured[2].headers.Authorization, 'Bearer test-key');
  assert.strictEqual(result.message.content, '测试成功');
  assert.strictEqual(result.usage.total_tokens, 12);
  assert.strictEqual(client.configuration().anthropicBaseUrl, 'https://provider.example/anthropic');
  assert.strictEqual(client.configuration().apiKeyConfigured, true);
  assert.strictEqual(Object.hasOwn(client.configuration(), 'apiKey'), false);
}


async function testMissingSecretIsRejectedBeforeNetworkCall() {
  const client = createDeepSeekClient({
    env: { DEEPSEEK_OPENAI_BASE_URL: 'https://provider.example' },
    httpClient: { post: async () => assert.fail('不应发送请求') },
  });
  await assert.rejects(() => client.chat([]), /DEEPSEEK_API_KEY/);
}


async function main() {
  await testOpenAICompatibleRequestContract();
  await testMissingSecretIsRejectedBeforeNetworkCall();
  console.log('DeepSeek client tests passed');
}


main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
