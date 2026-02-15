/**
 * Simulation Results Polling
 * Polls the GetSimulationResults endpoint and displays streaming results
 */

function initSimulationResults() {
    let pollCount = 0;
    const maxPolls = 30; // Poll for 30 seconds max
    const pollInterval = 250; // Poll every 250ms for faster updates
    
    function pollResults() {
        if (pollCount >= maxPolls) {
            const stream = document.getElementById('results-stream');
            if (stream && stream.innerHTML.trim() === '') {
                stream.innerHTML = '<span class="text-yellow-400">No results received. Check Logstash logs.</span>';
            }
            return;
        }
        
        fetch('/API/GetSimulationResults/')
            .then(response => response.json())
            .then(data => {
                console.log('Poll response:', data);
                console.log('Results count:', data.results ? data.results.length : 0);
                
                if (data.results && data.results.length > 0) {
                    console.log('Processing', data.results.length, 'events');
                    const stream = document.getElementById('results-stream');
                    console.log('Stream element:', stream);
                    
                    if (stream) {
                        data.results.forEach(event => {
                            const eventStr = JSON.stringify(event, null, 2);
                            stream.innerHTML += eventStr + '\n\n---\n\n';
                        });
                        stream.scrollTop = stream.scrollHeight;
                        console.log('Updated stream innerHTML length:', stream.innerHTML.length);
                    } else {
                        console.error('results-stream element not found!');
                    }
                }
                
                pollCount++;
                setTimeout(pollResults, pollInterval);
            })
            .catch(error => {
                console.error('Error polling results:', error);
                pollCount++;
                setTimeout(pollResults, pollInterval);
            });
    }
    
    // Start polling immediately
    setTimeout(pollResults, 100);
}
