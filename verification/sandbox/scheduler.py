import json
import subprocess
import os

def run_tests(config_file):
    # Load the test plan
    with open(config_file, 'r') as f:
        config = json.load(f)

    print(f"Loaded {len(config['test_suites'])} test suites.")

    for suite in config['test_suites']:
        print(f"\n{'='*50}")
        print(f"🚀 Running Test Suite: {suite['name']}")
        print(f"{'='*50}")

        # 1. Copy the current environment variables
        env = os.environ.copy()
        
        # 2. Inject our JSON parameters into the environment
        env['TEST_TYPE'] = suite['test_type']
        env['PRECISION'] = str(suite['precision'])
        env['NUM_CYCLES'] = str(suite['num_cycles'])
        env['RANDOM_SEED'] = str(suite['seed'])

        # Tell cocotb EXACTLY which test function to run so it doesn't run everything
        if suite['test_type'] == 'smoke':
            env['TESTCASE'] = 'test_mac_smoke'
        else:
            env['TESTCASE'] = 'test_mac_random_math'

        # 3. Call the cocotb Makefile. 
        # (Assuming your Makefile is in the same directory)
        result = subprocess.run(['make', 'clean', 'sim'], env=env)

        # 4. Check for success/failure
        if result.returncode != 0:
            print(f"❌ FAILED: Suite {suite['name']} encountered an error.")
            # Optional: break here if you want it to stop on the first failure
        else:
            print(f"✅ PASSED: Suite {suite['name']} completed successfully.")

if __name__ == "__main__":
    run_tests("input.json")