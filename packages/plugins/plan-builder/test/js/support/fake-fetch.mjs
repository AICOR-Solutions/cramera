/**
 * A stand-in for `fetch` that answers from a table and records every request.
 */

// %% fetch

export class FakeFetch {
  /**
   * @param {Object<string, *>} answers The JSON answer of each URL; a `FakeRefusal`
   *   answers with an error.
   */
  constructor(answers = {}) {
    this.answers = answers;
    this.requests = [];
    this.fetch = (url, options = {}) => this.answer(url, options);
  }

  async answer(url, options) {
    this.requests.push({ url, method: options.method, body: options.body === undefined ? undefined : JSON.parse(options.body) });
    const answer = this.answers[url];
    if (answer === undefined) return new FakeResponse(404, { error: `no answer for ${url}` }, 'Not Found');
    if (answer instanceof FakeRefusal) return new FakeResponse(answer.status, answer.body, answer.statusText);
    return new FakeResponse(200, typeof answer === 'function' ? answer(options) : structuredClone(answer));
  }

  /**
   * @param {string} url A URL.
   * @returns {Array<Object>} The requests sent to it.
   */
  sentTo(url) {
    return this.requests.filter((request) => request.url === url);
  }
}

export class FakeRefusal {
  constructor(status, body = null, statusText = 'Refused') {
    this.status = status;
    this.body = body;
    this.statusText = statusText;
  }
}

class FakeResponse {
  constructor(status, body, statusText = 'OK') {
    this.status = status;
    this.ok = status < 400;
    this.statusText = statusText;
    this.body = body;
    this.headers = { get: () => (body === null ? 'text/plain' : 'application/json') };
  }

  async json() {
    return this.body;
  }
}
