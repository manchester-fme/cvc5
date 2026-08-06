#!/usr/bin/env python3
"""
Coverage Mapper for cvc5
Processes tests using ctest and extracts coverage data using fastcov.

Test discovery/execution (get_ctest_tests, process_single_test) are cvc5's
own - CTest introspection, not something every solver shares. Everything
else (fastcov parsing, demangling, memory bookkeeping) is genuinely
identical across solvers and lives in CAST's coverage_mapper_utils.py -
see that file for why.
"""

import os
import sys
import json
import subprocess
import re
import argparse
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.environ['GITHUB_WORKSPACE'], 'src', 'coverage'))
from coverage_mapper_utils import (
    check_memory_limit,
    cleanup_memory,
    extract_coverage_data,
    get_memory_usage_mb,
    reset_coverage_counters,
    write_intermediate_mapping,
)


class CoverageMapper:
    def __init__(self, build_dir: str = "build"):
        self.build_dir = Path(build_dir)
        # Pre-compile regex for better performance
        self.test_regex = re.compile(r'Test\s+#(\d+):\s*(.+)')
        # Cache for demangled names to avoid repeated subprocess calls
        self.demangle_cache = {}
        # Memory monitoring
        self.max_memory_mb = 10000  # 10GB limit
        self.memory_check_interval = 50  # Check every 50 tests

    def get_ctest_tests(self) -> List[Tuple[int, str]]:
        """Get list of tests from ctest --show-only"""
        try:
            result = subprocess.run(["ctest", "--show-only"], cwd=self.build_dir,
                                  capture_output=True, text=True)

            if result.returncode != 0:
                print(f"Error running ctest --show-only: {result.stderr}")
                sys.stdout.flush()
                return []

            tests = []
            for line in result.stdout.split('\n'):
                match = self.test_regex.match(line.strip())
                if match:
                    tests.append((int(match.group(1)), match.group(2)))

            print(f"Found {len(tests)} tests")
            sys.stdout.flush()
            return tests

        except Exception as e:
            print(f"Error getting ctest tests: {e}")
            sys.stdout.flush()
            return []

    def process_single_test(self, test_info: Tuple[int, str]) -> Optional[Dict]:
        """Process a single test using ctest and extract coverage data"""
        test_id, test_name = test_info

        # Clear existing .gcda files before running test
        for gcda in self.build_dir.rglob("*.gcda"):
            gcda.unlink()

        # Reset coverage counters
        reset_coverage_counters(self.build_dir)

        # Measure test execution time
        start_time = time.time()

        # Run the test using ctest with parallel execution
        result = subprocess.run(["ctest", "-I", f"{test_id},{test_id}", "-j4", "--output-on-failure"],
                          cwd=self.build_dir, capture_output=True, text=True, check=False)

        end_time = time.time()
        execution_time = round(end_time - start_time, 2)

        if result.returncode != 0:
            print(f"❌ {test_name} - {execution_time}s")
            return None

        # Extract coverage data
        coverage_data = extract_coverage_data(self.build_dir, test_name, self.demangle_cache)

        if coverage_data:
            print(f"✅ {test_name} - {len(coverage_data['functions'])} functions - {execution_time}s")
        else:
            print(f"❌ {test_name} - {execution_time}s")
        sys.stdout.flush()

        # Clean up memory after each test
        cleanup_memory(self.demangle_cache)

        return coverage_data

    def process_tests(self, tests: List[Tuple[int, str]], max_tests: int = None) -> str:
        """Process tests sequentially with streaming to disk to avoid memory issues"""
        if max_tests:
            tests = tests[:max_tests]

        print(f"🚀 Processing {len(tests)} tests")
        print(f"💾 Memory limit: {self.max_memory_mb}MB")
        sys.stdout.flush()

        # Use streaming approach - write to disk incrementally
        temp_file = self.build_dir / "coverage_temp.json"
        function_to_tests = {}

        for i, test_info in enumerate(tests, 1):
            test_id, test_name = test_info
            print(f"Test {i}/{len(tests)} (ctest #{test_id}): {test_name}")
            sys.stdout.flush()

            # Check memory every N tests
            if i % self.memory_check_interval == 0:
                if not check_memory_limit(self.max_memory_mb):
                    print(f"🛑 Stopping at test {i} due to memory limit")
                    sys.stdout.flush()
                    break
                cleanup_memory(self.demangle_cache)
                memory_mb = get_memory_usage_mb()
                print(f"💾 Memory usage: {memory_mb:.1f}MB")
                sys.stdout.flush()

            result = self.process_single_test(test_info)
            if result:
                # Add to mapping immediately and don't keep in memory
                test_name = result["test_name"]
                for func in result["functions"]:
                    if func not in function_to_tests:
                        function_to_tests[func] = []
                    function_to_tests[func].append(test_name)

                # Write intermediate results every 100 tests to avoid losing progress
                if i % 100 == 0:
                    write_intermediate_mapping(function_to_tests, temp_file)

        # Write final mapping
        write_intermediate_mapping(function_to_tests, temp_file)
        return str(temp_file)


    def run(self, max_tests: int = None, test_pattern: str = None, start_index: int = None, end_index: int = None):
        """Main execution method"""
        print("🔍 Discovering tests...")
        sys.stdout.flush()
        tests = self.get_ctest_tests()

        if not tests:
            print("❌ No tests found")
            sys.stdout.flush()
            return

        if test_pattern:
            tests = [t for t in tests if test_pattern in t[1]]
            print(f"🔍 Filtered to {len(tests)} tests matching pattern: {test_pattern}")
            sys.stdout.flush()

        # Handle test range selection (1-based indexing to match ctest)
        if start_index is not None and end_index is not None:
            # Convert 1-based to 0-based for slicing
            start_idx = max(0, start_index - 1)
            end_idx = min(len(tests), end_index)
            tests = tests[start_idx:end_idx]
            print(f"🔍 Selected tests {start_index}-{end_index}: {len(tests)} tests")
            sys.stdout.flush()
        elif max_tests:
            tests = tests[:max_tests]
            print(f"🔍 Limited to {len(tests)} tests")
            sys.stdout.flush()

        # Process tests with streaming to avoid memory issues
        temp_file = self.process_tests(tests, max_tests)

        if not temp_file or not Path(temp_file).exists():
            print("❌ No coverage data generated")
            sys.stdout.flush()
            return

        # Move temp file to final location
        output_file = f"coverage_mapping_{start_index}_{end_index}.json" if start_index is not None else "coverage_mapping.json"
        Path(temp_file).rename(output_file)

        # Get stats from the final file
        with open(output_file, 'r') as f:
            coverage_mapping = json.load(f)

        print(f"📄 Coverage mapping saved to {output_file}")
        print(f"📊 Total functions: {len(coverage_mapping)}")
        print(f"📊 Total tests: {len(tests)}")
        sys.stdout.flush()

def main():
    parser = argparse.ArgumentParser(description='Coverage Mapper for cvc5')
    parser.add_argument('--build-dir', default='build', help='Build directory path')
    parser.add_argument('--max-tests', type=int, help='Maximum number of tests to process')
    parser.add_argument('--test-pattern', help='Filter tests by pattern')
    parser.add_argument('--start-index', type=int, help='Start index for test range (1-based, matches ctest numbering)')
    parser.add_argument('--end-index', type=int, help='End index for test range (1-based, inclusive)')

    args = parser.parse_args()

    mapper = CoverageMapper(args.build_dir)
    mapper.run(max_tests=args.max_tests, test_pattern=args.test_pattern,
               start_index=args.start_index, end_index=args.end_index)

if __name__ == "__main__":
    main()
