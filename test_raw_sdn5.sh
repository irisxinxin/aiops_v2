#!/bin/bash

echo "=== Raw sdn5_cpu Tests with Full Response Capture ==="
echo "Start time: $(date)"
echo ""

# Create output directory
mkdir -p test_outputs

# Function to run a single test
run_raw_test() {
    local test_num=$1
    echo "=== TEST #$test_num - $(date) ==="
    
    # Check connection pool
    echo "Connection Pool:"
    curl -s http://localhost:8081/healthz | jq '.connection_pool'
    
    echo ""
    echo "PROMPT SENT TO Q:"
    echo "Text: 第${test_num}次分析sdn5 CPU告警，请详细分析根因并给出解决建议"
    echo "Alert: sdn5 container CPU usage is too high (current: 0.92, threshold: 0.9)"
    
    # Prepare payload
    cat > test_outputs/payload_${test_num}.json << EOF
{
  "text": "第${test_num}次分析sdn5 CPU告警，请详细分析根因并给出解决建议",
  "alert": {
    "status": "firing",
    "env": "dev",
    "service": "sdn5",
    "category": "cpu", 
    "severity": "critical",
    "title": "sdn5 container CPU usage is too high",
    "metadata": {
      "current_value": 0.92,
      "threshold_value": 0.9,
      "pod": "omada-device-gateway-6.0.0189-59ccd49449-98n7b",
      "container": "omada-device-gateway"
    }
  }
}
EOF
    
    echo ""
    echo "RESPONSE FROM Q:"
    echo "Saving to test_outputs/response_${test_num}.txt..."
    
    # Record start time
    start_time=$(date +%s.%N)
    
    # Run curl and save response
    timeout 90 curl -X POST http://localhost:8081/ask \
        -H "Content-Type: application/json" \
        -d @test_outputs/payload_${test_num}.json \
        -w "\n\n=== TIMING INFO ===\nTotal: %{time_total}s\nConnect: %{time_connect}s\nResponse: %{time_starttransfer}s\nHTTP: %{http_code}\n" \
        > test_outputs/response_${test_num}.txt 2>&1
    
    # Calculate total time
    end_time=$(date +%s.%N)
    total_time=$(echo "$end_time - $start_time" | bc -l)
    
    echo "Total execution time: ${total_time}s"
    
    # Analyze response
    if [ -f test_outputs/response_${test_num}.txt ]; then
        echo ""
        echo "RESPONSE ANALYSIS:"
        
        # Check for historical references
        hist_refs=$(grep -i -E "(第[0-9]+次|previous|之前|历史|earlier|last.*analysis|prior|再次|multiple.*times)" test_outputs/response_${test_num}.txt | wc -l)
        if [ $hist_refs -gt 0 ]; then
            echo "✅ Historical context found ($hist_refs references)"
            grep -i -E "(第[0-9]+次|previous|之前|历史|earlier|last.*analysis|prior|再次|multiple.*times)" test_outputs/response_${test_num}.txt | head -3
        else
            echo "❌ No historical context detected"
        fi
        
        # Check for root cause analysis
        if grep -q -i -E "(false.*positive|root.*cause|根因|虚假|误报)" test_outputs/response_${test_num}.txt; then
            echo "✅ Root cause analysis present"
        else
            echo "❌ No root cause analysis found"
        fi
        
        # Check for analysis completion
        if grep -q -E "(analysis_complete|analysis.*summary)" test_outputs/response_${test_num}.txt; then
            echo "✅ Analysis completed"
        else
            echo "❌ Analysis incomplete or timeout"
        fi
        
        # Show last few lines of response
        echo ""
        echo "Response tail (last 10 lines):"
        tail -10 test_outputs/response_${test_num}.txt
    else
        echo "❌ No response file generated"
    fi
    
    echo ""
    echo "----------------------------------------"
}

# Run 3 tests
for i in {1..3}; do
    run_raw_test $i
    if [ $i -lt 3 ]; then
        echo "Waiting 10 seconds before next test..."
        sleep 10
    fi
done

echo ""
echo "=== SUMMARY ==="
echo "All responses saved to test_outputs/ directory"
echo "Files generated:"
ls -la test_outputs/

echo ""
echo "=== RESPONSE CORRECTNESS CHECK ==="
for i in {1..3}; do
    if [ -f test_outputs/response_${i}.txt ]; then
        echo "Test #$i response size: $(wc -c < test_outputs/response_${i}.txt) bytes"
        
        # Check if it contains structured analysis
        if grep -q "root_cause" test_outputs/response_${i}.txt; then
            echo "  ✅ Contains structured analysis"
        else
            echo "  ❌ Missing structured analysis"
        fi
    fi
done
