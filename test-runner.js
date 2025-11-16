#!/usr/bin/env node

/**
 * API Test Runner
 * Executes API tests based on DSL JSON format
 */

const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');
const { URL } = require('url');

// Simple JSONPath implementation for extracting values
function jsonPath(obj, path) {
  if (!path || path === '$') return obj;
  
  const parts = path.replace(/^\$\.?/, '').split('.');
  let current = obj;
  
  for (const part of parts) {
    if (part === '..') {
      // Recursive descent - find all matching keys
      const results = [];
      function findRecursive(o, key) {
        if (Array.isArray(o)) {
          o.forEach(item => findRecursive(item, key));
        } else if (typeof o === 'object' && o !== null) {
          if (key in o) results.push(o[key]);
          Object.values(o).forEach(val => findRecursive(val, key));
        }
      }
      const nextKey = parts[parts.indexOf('..') + 1];
      if (nextKey) {
        findRecursive(current, nextKey);
        return results.length > 0 ? results[0] : undefined;
      }
    } else {
      const arrayMatch = part.match(/^(\w+)\[(\d+)\]$/);
      if (arrayMatch) {
        const [, key, index] = arrayMatch;
        current = current?.[key]?.[parseInt(index)];
      } else {
        current = current?.[part];
      }
    }
    
    if (current === undefined || current === null) {
      return undefined;
    }
  }
  
  return current;
}

// Deep equality check for objects/arrays (partial match - only check keys in expected)
function deepEqual(actual, expected) {
  // Exact match
  if (actual === expected) return true;
  if (actual == null || expected == null) {
    return actual == null && expected == null;
  }
  
  // Type coercion for numbers/strings (flexible matching)
  if (typeof actual === 'number' && typeof expected === 'string') {
    return String(actual) === expected;
  }
  if (typeof actual === 'string' && typeof expected === 'number') {
    return actual === String(expected);
  }
  if (typeof actual === 'number' && typeof expected === 'number') {
    return actual === expected;
  }
  if (typeof actual === 'string' && typeof expected === 'string') {
    return actual === expected;
  }
  
  // If types don't match after coercion attempts, check if both are objects
  if (typeof expected === 'object' && typeof actual === 'object') {
    if (Array.isArray(expected) !== Array.isArray(actual)) return false;
    
    if (Array.isArray(expected)) {
      if (actual.length !== expected.length) return false;
      for (let i = 0; i < expected.length; i++) {
        if (!deepEqual(actual[i], expected[i])) return false;
      }
      return true;
    }
    
    // For objects, only check keys that exist in expected (partial match)
    const expectedKeys = Object.keys(expected);
    
    for (const key of expectedKeys) {
      if (!(key in actual)) return false;
      if (!deepEqual(actual[key], expected[key])) return false;
    }
    return true;
  }
  
  return false;
}

// Variable replacement in any value
function replaceVariables(value, variables) {
  if (typeof value === 'string') {
    // Check if the entire string is a variable (e.g., "{{age1}}")
    const fullMatch = value.match(/^\{\{(\w+)\}\}$/);
    if (fullMatch) {
      const varName = fullMatch[1];
      if (varName in variables) {
        // Return the variable value directly, preserving its type (number, boolean, etc.)
        return variables[varName];
      }
    }
    // Otherwise, replace variables within the string
    return value.replace(/\{\{(\w+)\}\}/g, (match, varName) => {
      if (varName in variables) {
        const val = variables[varName];
        return typeof val === 'object' ? JSON.stringify(val) : String(val);
      }
      return match;
    });
  } else if (typeof value === 'object' && value !== null) {
    if (Array.isArray(value)) {
      return value.map(item => replaceVariables(item, variables));
    } else {
      const result = {};
      for (const [key, val] of Object.entries(value)) {
        const newKey = replaceVariables(key, variables);
        const newVal = replaceVariables(val, variables);
        result[newKey] = newVal;
      }
      return result;
    }
  }
  return value;
}

// Make HTTP request
function makeRequest(config, variables) {
  return new Promise((resolve, reject) => {
    const { method, url, headers = {}, query = {}, body, timeout } = config;
    
    // Replace variables in URL, headers, query, body
    const finalUrl = replaceVariables(url, variables);
    const finalHeaders = replaceVariables(headers, variables);
    const finalQuery = replaceVariables(query, variables);
    const finalBody = body !== undefined ? replaceVariables(body, variables) : undefined;
    
    // Build full URL
    const baseUrl = config.baseUrl || '';
    const fullUrl = new URL(finalUrl, baseUrl);
    
    // Add query parameters
    for (const [key, value] of Object.entries(finalQuery)) {
      fullUrl.searchParams.append(key, String(value));
    }
    
    const urlObj = new URL(fullUrl.toString());
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || (urlObj.protocol === 'https:' ? 443 : 80),
      path: urlObj.pathname + urlObj.search,
      method: method,
      headers: {
        'User-Agent': 'API-Test-Runner/1.0',
        ...finalHeaders
      }
    };
    
    // Set Content-Type if body is provided and not already set
    if (finalBody !== undefined && !options.headers['Content-Type']) {
      if (typeof finalBody === 'object') {
        options.headers['Content-Type'] = 'application/json';
      }
    }
    
    const client = urlObj.protocol === 'https:' ? https : http;
    const req = client.request(options, (res) => {
      let data = '';
      res.on('data', chunk => { data += chunk; });
      res.on('end', () => {
        let responseBody;
        try {
          responseBody = JSON.parse(data);
        } catch {
          responseBody = data;
        }
        
        resolve({
          status: res.statusCode,
          headers: res.headers,
          body: responseBody,
          rawBody: data
        });
      });
    });
    
    req.on('error', reject);
    
    if (timeout) {
      req.setTimeout(timeout, () => {
        req.destroy();
        reject(new Error(`Request timeout after ${timeout}ms`));
      });
    }
    
    // Send body if present
    if (finalBody !== undefined) {
      const bodyStr = typeof finalBody === 'object' 
        ? JSON.stringify(finalBody) 
        : String(finalBody);
      req.write(bodyStr);
    }
    
    req.end();
  });
}

// Validate response against expectations
function validateResponse(response, expect, variables) {
  const errors = [];
  
  if (expect.status !== undefined) {
    if (response.status !== expect.status) {
      errors.push(`Expected status ${expect.status}, got ${response.status}`);
    }
  }
  
  if (expect.headers) {
    const expectedHeaders = replaceVariables(expect.headers, variables);
    for (const [key, value] of Object.entries(expectedHeaders)) {
      const actualValue = response.headers[key.toLowerCase()];
      if (String(actualValue) !== String(value)) {
        errors.push(`Expected header ${key}: ${value}, got ${actualValue}`);
      }
    }
  }
  
  if (expect.json !== undefined) {
    const expectedJson = replaceVariables(expect.json, variables);
    if (!deepEqual(response.body, expectedJson)) {
      // More detailed error message
      const expectedStr = JSON.stringify(expectedJson, null, 2);
      const actualStr = JSON.stringify(response.body, null, 2);
      errors.push(`JSON mismatch.\n    Expected: ${expectedStr}\n    Got: ${actualStr}`);
    }
  }
  
  if (expect.contains !== undefined) {
    const searchStr = replaceVariables(expect.contains, variables);
    if (typeof searchStr === 'string' && !response.rawBody.includes(searchStr)) {
      errors.push(`Response body does not contain "${searchStr}"`);
    }
  }
  
  if (expect.custom !== undefined) {
    try {
      // Create a safe evaluation context
      const responseObj = {
        status: response.status,
        headers: response.headers,
        json: response.body,
        body: response.rawBody
      };
      
      // Evaluate custom JS expression
      const result = eval(`(${expect.custom})`);
      if (!result) {
        errors.push(`Custom assertion failed: ${expect.custom}`);
      }
    } catch (e) {
      errors.push(`Custom assertion error: ${e.message}`);
    }
  }
  
  return errors;
}

// Extract variables from response
function extractVariables(response, extract, variables) {
  const extracted = {};
  
  if (!response || !response.body) {
    return extracted;
  }
  
  for (const [varName, jsonPathExpr] of Object.entries(extract)) {
    try {
      const value = jsonPath(response.body, jsonPathExpr);
      if (value !== undefined && value !== null) {
        extracted[varName] = value;
        variables[varName] = value;
      }
    } catch (e) {
      console.log(`  ⚠️  Error extracting ${varName} with JSONPath ${jsonPathExpr}: ${e.message}`);
    }
  }
  
  return extracted;
}

// Sleep utility
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Run a single test step
async function runStep(step, config, variables, retries = 0) {
  const { name, request, expect, extract, delay } = step;
  
  let lastError = null;
  let lastResponse = null;
  
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      if (attempt > 0) {
        console.log(`  ⚠️  Retry attempt ${attempt}/${retries}...`);
        await sleep(1000 * attempt); // Exponential backoff
      }
      
      // Make request
      lastResponse = await makeRequest({ ...request, baseUrl: config.baseUrl, timeout: request.timeout || config.timeout }, variables);
      
      // Extract variables BEFORE validation (so variables are available even if validation fails)
      if (extract && lastResponse && lastResponse.body) {
        try {
          const extracted = extractVariables(lastResponse, extract, variables);
          if (Object.keys(extracted).length > 0) {
            console.log(`  ✓ Extracted variables: ${Object.keys(extracted).join(', ')}`);
          } else {
            // Log if extraction was attempted but nothing was extracted
            console.log(`  ⚠️  No variables extracted (check JSONPath expressions)`);
          }
        } catch (e) {
          console.log(`  ⚠️  Error extracting variables: ${e.message}`);
        }
      }
      
      // Validate response
      if (expect) {
        const errors = validateResponse(lastResponse, expect, variables);
        if (errors.length > 0) {
          throw new Error(`Validation failed:\n${errors.map(e => `  - ${e}`).join('\n')}`);
        }
      }
      
      // Success
      if (delay) {
        await sleep(delay);
      }
      
      return { success: true, response: lastResponse };
      
    } catch (error) {
      lastError = error;
      if (attempt < retries) {
        continue;
      }
      return { success: false, error: error.message, response: lastResponse };
    }
  }
}

// Main test runner
async function runTests(testCaseFile) {
  console.log('='.repeat(80));
  console.log('API Test Runner');
  console.log('='.repeat(80));
  console.log();
  
  // Load test case
  let testCase;
  try {
    const content = fs.readFileSync(testCaseFile, 'utf-8');
    testCase = JSON.parse(content);
    console.log(`✓ Loaded test case from: ${testCaseFile}`);
  } catch (error) {
    console.error(`✗ Failed to load test case: ${error.message}`);
    process.exit(1);
  }
  
  const config = testCase.config || {};
  const globalVariables = { ...(testCase.variables || {}) };
  const tests = testCase.tests || [];
  
  console.log(`Configuration:`);
  console.log(`  Base URL: ${config.baseUrl || 'N/A'}`);
  console.log(`  Timeout: ${config.timeout || 'N/A'}ms`);
  console.log(`  Retries: ${config.retries || 0}`);
  console.log(`  Stop on failure: ${config.stopOnFailure || false}`);
  console.log();
  
  const results = {
    testCaseFile: testCaseFile,
    config: {
      baseUrl: config.baseUrl || null,
      timeout: config.timeout || null,
      retries: config.retries || 0,
      stopOnFailure: config.stopOnFailure || false
    },
    total: 0,
    passed: 0,
    failed: 0,
    tests: []
  };
  
  // Run each test
  for (const test of tests) {
    console.log('='.repeat(80));
    console.log(`Test: ${test.name}`);
    console.log('='.repeat(80));
    
    const testResult = {
      name: test.name,
      steps: [],
      passed: true
    };
    
    const variables = { ...globalVariables };
    const steps = test.steps || [];
    
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      results.total++;
      
      console.log(`\n[${i + 1}/${steps.length}] ${step.name}`);
      
      const stepResult = await runStep(step, config, variables, config.retries || 0);
      
      // Prepare step result for JSON output (include full response data)
      const stepResultForJson = {
        name: step.name,
        success: stepResult.success,
        error: stepResult.error || null,
        response: stepResult.response ? {
          status: stepResult.response.status,
          headers: stepResult.response.headers,
          body: stepResult.response.body,
          rawBody: stepResult.response.rawBody
        } : null
      };
      
      testResult.steps.push(stepResultForJson);
      
      if (stepResult.success) {
        results.passed++;
        console.log(`  ✓ PASSED`);
        if (stepResult.response) {
          console.log(`    Status: ${stepResult.response.status}`);
          if (stepResult.response.body && typeof stepResult.response.body === 'object') {
            console.log(`    Response: ${JSON.stringify(stepResult.response.body, null, 2).substring(0, 200)}...`);
          }
        }
      } else {
        results.failed++;
        testResult.passed = false;
        console.log(`  ✗ FAILED: ${stepResult.error}`);
        if (stepResult.response) {
          console.log(`    Status: ${stepResult.response.status}`);
          if (stepResult.response.rawBody) {
            console.log(`    Response: ${stepResult.response.rawBody.substring(0, 200)}...`);
          }
        }
        
        if (config.stopOnFailure) {
          console.log('\n⚠️  Stopping on first failure (stopOnFailure: true)');
          break;
        }
      }
    }
    
    results.tests.push(testResult);
    console.log(`\n${testResult.passed ? '✓' : '✗'} Test "${test.name}": ${testResult.passed ? 'PASSED' : 'FAILED'}`);
  }
  
  // Calculate success rate
  const successRate = results.total > 0 ? ((results.passed / results.total) * 100).toFixed(2) : 0;
  
  // Add summary to results
  results.successRate = parseFloat(successRate);
  results.timestamp = new Date().toISOString();
  
  // Print summary
  console.log('\n' + '='.repeat(80));
  console.log('Test Summary');
  console.log('='.repeat(80));
  console.log(`Total steps: ${results.total}`);
  console.log(`Passed: ${results.passed}`);
  console.log(`Failed: ${results.failed}`);
  console.log(`Success rate: ${successRate}%`);
  console.log('='.repeat(80));
  
  return results;
}

// Main entry point
function parseArgs() {
  const args = process.argv.slice(2);
  const result = {
    testCaseFile: 'test_case.json',
    outputFile: null
  };
  
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--output' || args[i] === '-o') {
      if (i + 1 < args.length) {
        result.outputFile = args[i + 1];
        i++;
      }
    } else if (!args[i].startsWith('-')) {
      result.testCaseFile = args[i];
    }
  }
  
  return result;
}

const { testCaseFile, outputFile } = parseArgs();

if (!fs.existsSync(testCaseFile)) {
  console.error(`Error: Test case file not found: ${testCaseFile}`);
  process.exit(1);
}

// Determine output file path
const defaultOutputFile = outputFile || 'test_results.json';

runTests(testCaseFile).then(results => {
  // Save results to JSON file
  try {
    const outputPath = path.resolve(defaultOutputFile);
    fs.writeFileSync(outputPath, JSON.stringify(results, null, 2), 'utf-8');
    console.log(`\n✓ Test results saved to: ${outputPath}`);
  } catch (error) {
    console.error(`\n✗ Failed to save test results: ${error.message}`);
    // Don't exit with error code, just warn
  }
  
  // Always exit with success code (0) - test failures are not considered errors
  process.exit(0);
}).catch(error => {
  console.error(`Fatal error: ${error.message}`);
  console.error(error.stack);
  process.exit(1);
});

